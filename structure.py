"""RT structure set import helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pydicom

from .dicom_util import (
    check_dicom_image_type,
    float_or,
    image_orientation_axes,
    is_structure_file,
    positive_float_or,
)
from .node_groups import apply_structure_material
from .ui_utils import show_message_box
from .volume_utils import (
    align_object_to_ct_frame,
    find_ct_anchor,
    set_object_patient_transform,
    write_vdb_volume,
)


def _load_reference_image_slices(directory_path: Path, dicom_structure: pydicom.Dataset) -> list[pydicom.Dataset]:
    referenced_series_uids: set[str] = set()
    referenced_sop_uids: set[str] = set()

    try:
        frame_refs = dicom_structure.ReferencedFrameOfReferenceSequence
        for frame_ref in frame_refs:
            rt_study_refs = getattr(frame_ref, "RTReferencedStudySequence", [])
            for study_ref in rt_study_refs:
                rt_series_refs = getattr(study_ref, "RTReferencedSeriesSequence", [])
                for series_ref in rt_series_refs:
                    series_uid = getattr(series_ref, "SeriesInstanceUID", None)
                    if series_uid:
                        referenced_series_uids.add(str(series_uid))
                    contour_images = getattr(series_ref, "ContourImageSequence", [])
                    for contour_image in contour_images:
                        sop_uid = getattr(contour_image, "ReferencedSOPInstanceUID", None)
                        if sop_uid:
                            referenced_sop_uids.add(str(sop_uid))
    except Exception:
        # Fall back to modality/series matching when reference metadata is incomplete.
        pass

    # Some exporters omit the series-level ContourImageSequence but retain the
    # image references on each individual contour. Use those references to
    # resolve the series rather than treating every CT/MR in the folder as one
    # image stack.
    for roi_contour in getattr(dicom_structure, "ROIContourSequence", []):
        for contour in getattr(roi_contour, "ContourSequence", []):
            for contour_image in getattr(contour, "ContourImageSequence", []):
                sop_uid = getattr(contour_image, "ReferencedSOPInstanceUID", None)
                if sop_uid:
                    referenced_sop_uids.add(str(sop_uid))

    candidates: list[pydicom.Dataset] = []
    seen_sop_uids: set[str] = set()
    for file_path in sorted(directory_path.iterdir()):
        if not file_path.is_file():
            continue
        try:
            ds = pydicom.dcmread(file_path, stop_before_pixels=True)
        except Exception:
            continue
        if not check_dicom_image_type(ds):
            continue
        sop_uid = str(getattr(ds, "SOPInstanceUID", ""))
        if not hasattr(ds, "ImagePositionPatient") or not hasattr(ds, "ImageOrientationPatient"):
            continue
        # Copies of the same slice (``IMG1.dcm`` and ``IMG1 (1).dcm``) would
        # otherwise inflate the slice count and allocate a mask grid deeper
        # than the series, the same way load_dicom_series guards the CT path.
        if sop_uid:
            if sop_uid in seen_sop_uids:
                continue
            seen_sop_uids.add(sop_uid)
        candidates.append(ds)

    if len(referenced_series_uids) > 1:
        raise ValueError(
            "The RT Structure Set explicitly references multiple CT/MR series."
        )
    if referenced_series_uids:
        referenced_series_uid = next(iter(referenced_series_uids))
        return [
            ds
            for ds in candidates
            if str(getattr(ds, "SeriesInstanceUID", "")) == referenced_series_uid
        ]

    if referenced_sop_uids:
        referenced_series = {
            str(getattr(ds, "SeriesInstanceUID", ""))
            for ds in candidates
            if str(getattr(ds, "SOPInstanceUID", "")) in referenced_sop_uids
        }
        referenced_series.discard("")
        if len(referenced_series) > 1:
            raise ValueError(
                "The RT Structure Set references images from multiple CT/MR series."
            )
        if len(referenced_series) == 1:
            selected_uid = next(iter(referenced_series))
            return [
                ds
                for ds in candidates
                if str(getattr(ds, "SeriesInstanceUID", "")) == selected_uid
            ]
        return []

    series_uids = {str(getattr(ds, "SeriesInstanceUID", "")) for ds in candidates}
    if len(series_uids) > 1:
        raise ValueError(
            "The RT Structure Set does not identify its reference image series, "
            "and multiple CT/MR series are present in the selected directory."
        )
    if series_uids == {""}:
        return []

    return candidates


def _build_geometry(image_slices: list[pydicom.Dataset]):
    if not image_slices:
        raise ValueError("No referenced CT/MR slices were found for this RT Structure Set.")

    first = image_slices[0]
    orientation = np.asarray(getattr(first, "ImageOrientationPatient", [1, 0, 0, 0, 1, 0]), dtype=float)
    if orientation.size != 6:
        raise ValueError("Invalid ImageOrientationPatient in referenced images.")

    try:
        row_dir, col_dir, normal_dir = image_orientation_axes(orientation)
    except ValueError as exc:
        raise ValueError(f"Invalid orientation vectors in referenced images: {exc}") from exc

    # Sort slices along the slice normal direction.
    positions = []
    for slice_number, image_slice in enumerate(image_slices, start=1):
        try:
            position = np.asarray(image_slice.ImagePositionPatient, dtype=float).reshape(-1)
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError(
                f"Referenced image {slice_number} has invalid ImagePositionPatient."
            ) from exc
        if position.size != 3 or not np.all(np.isfinite(position)):
            raise ValueError(
                f"Referenced image {slice_number} has invalid ImagePositionPatient."
            )
        positions.append(position)
    projections = [float(np.dot(position, normal_dir)) for position in positions]
    sorted_pairs = sorted(
        zip(projections, image_slices, strict=True), key=lambda pair: pair[0]
    )
    sorted_projections = [pair[0] for pair in sorted_pairs]
    sorted_slices = [pair[1] for pair in sorted_pairs]

    pixel_spacing = getattr(sorted_slices[0], "PixelSpacing", None) or [1.0, 1.0]
    if len(pixel_spacing) < 2:
        raise ValueError("Referenced images are missing PixelSpacing.")
    row_spacing = positive_float_or(pixel_spacing[0], 0.0)
    col_spacing = positive_float_or(pixel_spacing[1], 0.0)
    if row_spacing <= 0 or col_spacing <= 0:
        raise ValueError("Referenced images have invalid PixelSpacing.")

    fallback_thickness = positive_float_or(getattr(sorted_slices[0], "SliceThickness", None), 1.0)
    slice_spacing = fallback_thickness
    if len(sorted_projections) > 1:
        deltas = np.diff(np.asarray(sorted_projections))
        if not np.all(np.isfinite(deltas)) or np.any(np.abs(deltas) <= 1e-6):
            raise ValueError(
                "Referenced CT/MR slices contain duplicate or invalid positions."
            )
        slice_spacing = float(np.median(np.abs(deltas)))
        if not np.allclose(np.abs(deltas), slice_spacing, rtol=1e-4, atol=1e-3):
            spacing_text = ", ".join(f"{value:.3g}" for value in np.abs(deltas[:6]))
            if len(deltas) > 6:
                spacing_text += ", ..."
            raise ValueError(
                "Referenced CT/MR slice spacing is non-uniform "
                f"({spacing_text} mm). MedBlend cannot rasterise structures onto "
                "a linearly transformed VDB grid without resampling."
            )
    if slice_spacing <= 0:
        slice_spacing = 1.0

    origin = np.asarray(sorted_slices[0].ImagePositionPatient, dtype=float)
    rows = int(getattr(sorted_slices[0], "Rows", 0))
    cols = int(getattr(sorted_slices[0], "Columns", 0))
    if rows <= 0 or cols <= 0:
        raise ValueError("Referenced images have invalid Rows/Columns.")

    for slice_number, image_slice in enumerate(sorted_slices[1:], start=2):
        current_rows = int(getattr(image_slice, "Rows", 0))
        current_cols = int(getattr(image_slice, "Columns", 0))
        if (current_rows, current_cols) != (rows, cols):
            raise ValueError(
                f"Referenced image {slice_number} has Rows/Columns "
                f"{current_rows}x{current_cols}, expected {rows}x{cols}."
            )

        try:
            current_orientation = np.asarray(
                image_slice.ImageOrientationPatient, dtype=float
            )
            current_spacing = np.asarray(image_slice.PixelSpacing, dtype=float)
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError(
                f"Referenced image {slice_number} has invalid orientation or spacing."
            ) from exc
        if (
            current_orientation.size != 6
            or not np.all(np.isfinite(current_orientation))
            or not np.allclose(current_orientation, orientation, rtol=1e-5, atol=1e-6)
        ):
            raise ValueError(
                f"Referenced image {slice_number} has inconsistent ImageOrientationPatient."
            )
        if (
            current_spacing.size < 2
            or not np.all(np.isfinite(current_spacing[:2]))
            or not np.allclose(
                current_spacing[:2], [row_spacing, col_spacing], rtol=1e-4, atol=1e-3
            )
        ):
            raise ValueError(
                f"Referenced image {slice_number} has inconsistent PixelSpacing."
            )

    # Basis for [row_index, col_index, slice_index] coordinates.
    row_axis = col_dir * row_spacing
    col_axis = row_dir * col_spacing
    slice_axis = normal_dir * slice_spacing
    basis = np.column_stack((row_axis, col_axis, slice_axis))
    inv_basis = np.linalg.inv(basis)

    return {
        "origin": origin,
        "inv_basis": inv_basis,
        "basis": basis,
        "rows": rows,
        "cols": cols,
        "num_slices": len(sorted_slices),
        "spacing": (slice_spacing, row_spacing, col_spacing),
        "vdb_basis": np.column_stack((slice_axis, row_axis, col_axis)),
        "slice_axis_dir": slice_axis / np.linalg.norm(slice_axis),
        "row_axis_dir": row_axis / np.linalg.norm(row_axis),
        "col_axis_dir": col_axis / np.linalg.norm(col_axis),
    }


def _iter_contour_points(dicom_structure: pydicom.Dataset):
    for roi_contour in getattr(dicom_structure, "ROIContourSequence", []):
        for contour in getattr(roi_contour, "ContourSequence", []):
            contour_data = getattr(contour, "ContourData", None)
            if not contour_data or len(contour_data) < 9 or (len(contour_data) % 3) != 0:
                continue
            points_xyz = np.asarray(contour_data, dtype=float).reshape((-1, 3))
            if points_xyz.shape[0] >= 3:
                yield points_xyz


def _build_geometry_from_contours(dicom_structure: pydicom.Dataset):
    contour_sets = list(_iter_contour_points(dicom_structure))
    if not contour_sets:
        raise ValueError("No valid contour points found in this RT Structure Set.")

    all_points = np.concatenate(contour_sets, axis=0)
    centroid = np.mean(all_points, axis=0)

    normal_dir = None
    for points in contour_sets:
        base = points[0]
        for index in range(1, points.shape[0] - 1):
            v1 = points[index] - base
            v2 = points[index + 1] - base
            normal = np.cross(v1, v2)
            norm = float(np.linalg.norm(normal))
            if norm > 1e-6:
                normal_dir = normal / norm
                break
        if normal_dir is not None:
            break

    if normal_dir is None:
        cov = np.cov((all_points - centroid).T)
        eigvals, eigvecs = np.linalg.eigh(cov)
        normal_dir = eigvecs[:, int(np.argmin(eigvals))]
        normal_dir = normal_dir / np.linalg.norm(normal_dir)

    row_axis_dir = None
    for points in contour_sets:
        edge_vectors = np.diff(np.vstack((points, points[0])), axis=0)
        for edge in edge_vectors:
            projected = edge - np.dot(edge, normal_dir) * normal_dir
            length = float(np.linalg.norm(projected))
            if length > 1e-6:
                row_axis_dir = projected / length
                break
        if row_axis_dir is not None:
            break

    if row_axis_dir is None:
        trial = np.asarray([1.0, 0.0, 0.0], dtype=float)
        if abs(float(np.dot(trial, normal_dir))) > 0.9:
            trial = np.asarray([0.0, 1.0, 0.0], dtype=float)
        row_axis_dir = trial - np.dot(trial, normal_dir) * normal_dir
        row_axis_dir = row_axis_dir / np.linalg.norm(row_axis_dir)

    col_axis_dir = np.cross(normal_dir, row_axis_dir)
    col_axis_dir = col_axis_dir / np.linalg.norm(col_axis_dir)
    row_axis_dir = np.cross(col_axis_dir, normal_dir)
    row_axis_dir = row_axis_dir / np.linalg.norm(row_axis_dir)

    row_spacing = 1.0
    col_spacing = 1.0

    row_coords = all_points @ row_axis_dir
    col_coords = all_points @ col_axis_dir
    slice_coords = all_points @ normal_dir

    min_row = float(np.min(row_coords))
    max_row = float(np.max(row_coords))
    min_col = float(np.min(col_coords))
    max_col = float(np.max(col_coords))

    contour_slice_positions = sorted(float(np.mean(points @ normal_dir)) for points in contour_sets)
    unique_slices = []
    for value in contour_slice_positions:
        if not unique_slices or abs(value - unique_slices[-1]) > 1e-3:
            unique_slices.append(value)

    if len(unique_slices) > 1:
        deltas = np.diff(np.asarray(unique_slices, dtype=float))
        non_zero = np.abs(deltas) > 1e-6
        if np.any(non_zero):
            slice_spacing = float(np.median(np.abs(deltas[non_zero])))
        else:
            slice_spacing = 1.0
        min_slice = float(unique_slices[0])
        max_slice = float(unique_slices[-1])
    else:
        slice_spacing = 1.0
        min_slice = float(np.min(slice_coords))
        max_slice = float(np.max(slice_coords))
    if slice_spacing <= 0:
        slice_spacing = 1.0

    rows = max(1, int(np.ceil((max_row - min_row) / row_spacing)) + 2)
    cols = max(1, int(np.ceil((max_col - min_col) / col_spacing)) + 2)
    num_slices = max(1, int(np.ceil((max_slice - min_slice) / slice_spacing)) + 1)

    origin = (
        (row_axis_dir * min_row)
        + (col_axis_dir * min_col)
        + (normal_dir * min_slice)
    )

    row_axis = row_axis_dir * row_spacing
    col_axis = col_axis_dir * col_spacing
    slice_axis = normal_dir * slice_spacing
    basis = np.column_stack((row_axis, col_axis, slice_axis))
    inv_basis = np.linalg.inv(basis)

    return {
        "origin": origin,
        "inv_basis": inv_basis,
        "basis": basis,
        "rows": rows,
        "cols": cols,
        "num_slices": num_slices,
        "spacing": (slice_spacing, row_spacing, col_spacing),
        "vdb_basis": np.column_stack((slice_axis, row_axis, col_axis)),
        "slice_axis_dir": slice_axis / np.linalg.norm(slice_axis),
        "row_axis_dir": row_axis / np.linalg.norm(row_axis),
        "col_axis_dir": col_axis / np.linalg.norm(col_axis),
    }


def _get_structure_frame_uid(dicom_structure: pydicom.Dataset) -> str:
    frame_uid = str(getattr(dicom_structure, "FrameOfReferenceUID", ""))
    if frame_uid:
        return frame_uid
    try:
        frame_refs = getattr(dicom_structure, "ReferencedFrameOfReferenceSequence", [])
        if frame_refs:
            return str(getattr(frame_refs[0], "FrameOfReferenceUID", ""))
    except Exception:
        pass
    return ""


def _polygon_mask(shape: tuple[int, int], polygon_rc: np.ndarray) -> np.ndarray:
    """Rasterise a closed polygon with the even-odd rule.

    Scanline based: an edge can only affect the rows it spans, so each row
    solves for its own crossings and fills by parity. Testing every edge
    against the whole bounding box instead costs O(edges x box area), which
    on a body/external contour (a near-full 512x512 box with hundreds of
    points) took over a second per slice and minutes per ROI.
    """

    rows, cols = shape
    if polygon_rc.shape[0] < 3:
        return np.zeros(shape, dtype=bool)

    poly_r = np.asarray(polygon_rc[:, 0], dtype=float)
    poly_c = np.asarray(polygon_rc[:, 1], dtype=float)

    min_r = max(int(np.floor(np.min(poly_r))), 0)
    max_r = min(int(np.ceil(np.max(poly_r))), rows - 1)
    min_c = max(int(np.floor(np.min(poly_c))), 0)
    max_c = min(int(np.ceil(np.max(poly_c))), cols - 1)
    mask = np.zeros(shape, dtype=bool)
    if min_r > max_r or min_c > max_c:
        return mask

    # Horizontal edges never cross a scanline and would divide by zero.
    r1, c1 = poly_r, poly_c
    r2, c2 = np.roll(poly_r, -1), np.roll(poly_c, -1)
    spans_rows = r1 != r2
    r1, c1, r2, c2 = r1[spans_rows], c1[spans_rows], r2[spans_rows], c2[spans_rows]
    if r1.size == 0:
        return mask

    # Integer indices are voxel centres (ImagePositionPatient references the
    # centre of the first voxel), so sample the polygon at integer coordinates.
    x = np.arange(min_c, max_c + 1, dtype=float)

    for row_index in range(min_r, max_r + 1):
        y = float(row_index)
        crossing = (r1 > y) != (r2 > y)
        if not crossing.any():
            continue
        y1, x1 = r1[crossing], c1[crossing]
        y2, x2 = r2[crossing], c2[crossing]
        crossings = np.sort((x2 - x1) * (y - y1) / (y2 - y1) + x1)
        # Inside where an odd number of crossings lies strictly to the right.
        to_the_right = crossings.size - np.searchsorted(crossings, x, side="right")
        mask[row_index, min_c : max_c + 1] = (to_the_right % 2) == 1

    return mask


def _contour_points_to_ijk(points_xyz: np.ndarray, origin: np.ndarray, inv_basis: np.ndarray) -> np.ndarray:
    diffs = points_xyz - origin
    return (inv_basis @ diffs.T).T


def _roi_display_color(roi_contour: pydicom.Dataset) -> tuple[float, float, float, float] | None:
    display_color = getattr(roi_contour, "ROIDisplayColor", None)
    if display_color is None:
        return None
    try:
        values = [float(component) for component in display_color]
    except (TypeError, ValueError):
        return None
    if len(values) < 3:
        return None
    return (values[0] / 255.0, values[1] / 255.0, values[2] / 255.0, 1.0)


def crop_mask_to_bounds(
    mask: np.ndarray, geometry
) -> tuple[np.ndarray, np.ndarray]:
    """Trim a full-grid mask to its occupied box and return the shifted origin.

    A structure typically fills a few percent of the CT grid, so writing every
    ROI at full grid extent produces hundreds of megabytes of almost-empty
    voxels per ROI. Cropping keeps the geometry identical by moving the origin
    to the patient position of the first retained voxel.

    The bounds come from three one-dimensional reductions rather than
    ``np.nonzero``, which would materialise three int64 indices per set voxel -
    more than twice the size of the mask itself on a large ROI.
    """

    origin = np.asarray(geometry["origin"], dtype=float)
    occupied_slices = np.any(mask, axis=(1, 2))
    if not occupied_slices.any():
        return mask, origin

    def _bounds(flags: np.ndarray) -> tuple[int, int]:
        indices = np.flatnonzero(flags)
        return int(indices[0]), int(indices[-1])

    slice_start, slice_end = _bounds(occupied_slices)
    row_start, row_end = _bounds(np.any(mask, axis=(0, 2)))
    col_start, col_end = _bounds(np.any(mask, axis=(0, 1)))
    cropped = mask[
        slice_start : slice_end + 1,
        row_start : row_end + 1,
        col_start : col_end + 1,
    ]

    # ``basis`` maps [row, col, slice] index offsets to patient millimetres.
    basis = np.asarray(geometry["basis"], dtype=float)
    shifted_origin = origin + basis @ np.asarray([row_start, col_start, slice_start], dtype=float)
    return np.ascontiguousarray(cropped), shifted_origin


def iter_roi_masks(dicom_structure: pydicom.Dataset, geometry):
    """Yield ``(roi_name, mask, color, skipped_contours)`` one ROI at a time.

    Masks are produced lazily and kept as ``bool`` so only a single ROI volume
    is resident at a time; materialising every ROI as ``float64`` up front cost
    64x the memory and ran out of RAM on full-resolution structure sets.

    ``mask`` is ``None`` when an ROI rasterised to nothing. Those are still
    yielded so the caller can report an ROI that was dropped entirely rather
    than letting it vanish from the import silently.

    ``skipped_contours`` counts contours that could not be rasterised at all -
    either outside the reconstructed slice range, or carrying coordinates that
    are not finite numbers.
    """

    roi_names = {}
    for roi in getattr(dicom_structure, "StructureSetROISequence", []):
        roi_number = int(float_or(getattr(roi, "ROINumber", -1), -1))
        roi_names[roi_number] = str(getattr(roi, "ROIName", "") or f"ROI_{roi_number}")

    rows = geometry["rows"]
    cols = geometry["cols"]
    num_slices = geometry["num_slices"]
    origin = geometry["origin"]
    inv_basis = geometry["inv_basis"]

    for roi_contour in getattr(dicom_structure, "ROIContourSequence", []):
        roi_number = int(float_or(getattr(roi_contour, "ReferencedROINumber", -1), -1))
        roi_name = roi_names.get(roi_number, f"ROI_{roi_number}")
        volume_mask = np.zeros((num_slices, rows, cols), dtype=bool)
        skipped = 0

        for contour in getattr(roi_contour, "ContourSequence", []):
            # Only closed planar contours describe filled regions; open
            # contours and single points must not be rasterized as polygons.
            # The tag is Type 1 but exports do leave it empty, and pydicom then
            # yields ``None`` - stringifying that gives "NONE", which matches no
            # known type and used to drop every contour of the ROI in silence.
            raw_geometric_type = getattr(contour, "ContourGeometricType", None)
            geometric_type = (
                str(raw_geometric_type).strip().upper() if raw_geometric_type else "CLOSED_PLANAR"
            )
            if geometric_type not in {"CLOSED_PLANAR", "CLOSEDPLANAR_XOR"}:
                continue
            # A corrupt coordinate would otherwise raise out of the rasteriser
            # and abandon every ROI still queued behind this one, so count the
            # contour and step over it instead. pydicom hands back the raw
            # strings of a malformed DS value rather than floats, so numpy is
            # where that surfaces.
            try:
                contour_data = getattr(contour, "ContourData", None)
                if not contour_data or len(contour_data) < 9 or len(contour_data) % 3 != 0:
                    continue
                points_xyz = np.asarray(contour_data, dtype=float).reshape((-1, 3))
            except (TypeError, ValueError):
                skipped += 1
                continue
            if not np.all(np.isfinite(points_xyz)):
                skipped += 1
                continue

            ijk = _contour_points_to_ijk(points_xyz, origin, inv_basis)

            slice_index = int(np.rint(np.mean(ijk[:, 2])))
            if slice_index < 0 or slice_index >= num_slices:
                # The contour lies outside the reconstructed slice range, which
                # happens when only part of the referenced series is present.
                skipped += 1
                continue

            polygon_rc = ijk[:, :2]
            polygon_mask = _polygon_mask((rows, cols), polygon_rc)

            # XOR composition matches typical RTSTRUCT contour hole semantics.
            volume_mask[slice_index] ^= polygon_mask

        color = _roi_display_color(roi_contour)
        if np.any(volume_mask):
            yield roi_name, volume_mask, color, skipped
        else:
            yield roi_name, None, color, skipped


def load_structures(file_path: Path) -> bool:
    structure_file_path = Path(file_path)
    directory_path = structure_file_path.parent

    try:
        dicom_structure = pydicom.dcmread(structure_file_path)
    except Exception as exc:
        show_message_box(f"Unable to read structure file: {exc}", "Error", "ERROR")
        return False

    if not is_structure_file(dicom_structure):
        show_message_box("Selected file is not an RT Structure Set.", "Error", "ERROR")
        return False

    try:
        image_slices = _load_reference_image_slices(directory_path, dicom_structure)
        if image_slices:
            geometry = _build_geometry(image_slices)
        else:
            geometry = _build_geometry_from_contours(dicom_structure)
    except Exception as exc:
        show_message_box(
            f"Unable to convert RT Structure contours: {exc}",
            "Error",
            "ERROR",
        )
        return False

    spacing = geometry["spacing"]
    frame_uid = _get_structure_frame_uid(dicom_structure)
    ct_anchor = find_ct_anchor(frame_uid)

    imported_count = 0
    failed_names: list[str] = []
    empty_names: list[str] = []
    # Collected rather than shown per ROI: a structure set whose volumes cannot
    # be written (no openvdb, unwritable temp directory) fails for every single
    # ROI, and one dialog each would bury the scene in popups.
    write_errors: list[str] = []
    skipped_contours = 0
    fatal_error = None

    try:
        roi_masks = iter_roi_masks(dicom_structure, geometry)
        for roi_name, mask, color, skipped in roi_masks:
            skipped_contours += skipped
            if mask is None:
                empty_names.append(roi_name)
                continue

            # Crop before writing so each ROI only occupies its own bounding
            # box rather than the whole CT grid.
            cropped, roi_origin = crop_mask_to_bounds(mask, geometry)
            del mask

            result = write_vdb_volume(
                cropped, spacing, f"{roi_name}.vdb", on_error=write_errors.append
            )
            if not result:
                # One unwritable ROI should not discard the ones that worked.
                failed_names.append(roi_name)
                continue
            _output_path, imported_obj = result

            if color:
                imported_obj.color = color
            imported_obj["medblend_roi_name"] = roi_name

            aligned = False
            if ct_anchor:
                aligned = align_object_to_ct_frame(
                    imported_obj,
                    ct_anchor,
                    roi_origin,
                    geometry["vdb_basis"],
                    spacing,
                )
            if not aligned:
                set_object_patient_transform(
                    imported_obj,
                    roi_origin,
                    geometry["slice_axis_dir"],
                    geometry["row_axis_dir"],
                    geometry["col_axis_dir"],
                )
            apply_structure_material(imported_obj, roi_name, color)
            imported_count += 1
    except Exception as exc:
        # Structures imported before the failure are already in the scene, so
        # report the error but keep them rather than reporting a clean cancel.
        fatal_error = exc

    if imported_count == 0:
        if fatal_error:
            message = f"Unable to convert RT Structure contours: {fatal_error}"
        elif write_errors:
            # Every ROI failed to write; the reason is the same for all of them
            # and would otherwise be lost now that it is no longer popped up.
            message = f"No structures could be written. {write_errors[0]}"
        else:
            message = "No contour masks were generated from this RT Structure Set."
        show_message_box(message, "Error", "ERROR")
        return False

    notes = []
    if fatal_error:
        notes.append(f"import stopped early: {fatal_error}")
    if failed_names:
        note = f"{len(failed_names)} structure(s) could not be written: {', '.join(failed_names[:5])}"
        if write_errors:
            note += f" ({write_errors[0]})"
        notes.append(note)
    if empty_names:
        notes.append(
            f"{len(empty_names)} structure(s) produced no voxels and were skipped: "
            f"{', '.join(empty_names[:5])}"
        )
    if skipped_contours:
        notes.append(
            f"{skipped_contours} contour(s) could not be rasterised and were skipped "
            "(outside the reconstructed slice range, or malformed coordinates)"
        )
    if notes:
        show_message_box(
            f"Imported {imported_count} structure(s). " + ". ".join(notes) + ".",
            "Structure Import Warnings",
            "INFO",
        )

    return True
