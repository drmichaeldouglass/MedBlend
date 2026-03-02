"""RT structure set import helpers."""

from __future__ import annotations

from pathlib import Path

import bpy
import numpy as np
import pydicom
from mathutils import Matrix

from .dicom_util import check_dicom_image_type, is_structure_file
from .node_groups import apply_dicom_shader
from .ui_utils import show_message_box
from .volume_utils import write_vdb_volume


def _load_reference_image_slices(directory_path: Path, dicom_structure: pydicom.Dataset) -> list[pydicom.Dataset]:
    referenced_series_uid = None
    referenced_sop_uids: set[str] = set()

    try:
        frame_refs = dicom_structure.ReferencedFrameOfReferenceSequence
        for frame_ref in frame_refs:
            rt_study_refs = getattr(frame_ref, "RTReferencedStudySequence", [])
            for study_ref in rt_study_refs:
                rt_series_refs = getattr(study_ref, "RTReferencedSeriesSequence", [])
                for series_ref in rt_series_refs:
                    series_uid = getattr(series_ref, "SeriesInstanceUID", None)
                    if series_uid and not referenced_series_uid:
                        referenced_series_uid = series_uid
                    contour_images = getattr(series_ref, "ContourImageSequence", [])
                    for contour_image in contour_images:
                        sop_uid = getattr(contour_image, "ReferencedSOPInstanceUID", None)
                        if sop_uid:
                            referenced_sop_uids.add(str(sop_uid))
    except Exception:
        # Fall back to modality/series matching when reference metadata is incomplete.
        pass

    image_slices: list[pydicom.Dataset] = []
    for file_path in directory_path.iterdir():
        if not file_path.is_file() or file_path.suffix.lower() != ".dcm":
            continue
        try:
            ds = pydicom.dcmread(file_path, stop_before_pixels=False)
        except Exception:
            continue
        if not check_dicom_image_type(ds):
            continue
        if referenced_series_uid and getattr(ds, "SeriesInstanceUID", None) != referenced_series_uid:
            continue
        if referenced_sop_uids:
            sop_uid = str(getattr(ds, "SOPInstanceUID", ""))
            if sop_uid and sop_uid not in referenced_sop_uids:
                continue
        if not hasattr(ds, "ImagePositionPatient") or not hasattr(ds, "ImageOrientationPatient"):
            continue
        image_slices.append(ds)

    return image_slices


def _build_geometry(image_slices: list[pydicom.Dataset]):
    if not image_slices:
        raise ValueError("No referenced CT/MR slices were found for this RT Structure Set.")

    first = image_slices[0]
    orientation = np.asarray(getattr(first, "ImageOrientationPatient", [1, 0, 0, 0, 1, 0]), dtype=float)
    if orientation.size != 6:
        raise ValueError("Invalid ImageOrientationPatient in referenced images.")

    row_dir = orientation[:3]
    col_dir = orientation[3:]
    normal_dir = np.cross(row_dir, col_dir)
    normal_norm = np.linalg.norm(normal_dir)
    if normal_norm == 0:
        raise ValueError("Invalid orientation vectors in referenced images.")
    normal_dir = normal_dir / normal_norm

    # Sort slices along the slice normal direction.
    projections = [float(np.dot(np.asarray(ds.ImagePositionPatient, dtype=float), normal_dir)) for ds in image_slices]
    sorted_pairs = sorted(zip(projections, image_slices), key=lambda pair: pair[0])
    sorted_projections = [pair[0] for pair in sorted_pairs]
    sorted_slices = [pair[1] for pair in sorted_pairs]

    pixel_spacing = getattr(sorted_slices[0], "PixelSpacing", [1.0, 1.0])
    if len(pixel_spacing) < 2:
        raise ValueError("Referenced images are missing PixelSpacing.")
    row_spacing = float(pixel_spacing[0])
    col_spacing = float(pixel_spacing[1])
    if row_spacing <= 0 or col_spacing <= 0:
        raise ValueError("Referenced images have invalid PixelSpacing.")

    if len(sorted_projections) > 1:
        deltas = np.diff(np.asarray(sorted_projections))
        non_zero = np.abs(deltas) > 1e-6
        if np.any(non_zero):
            slice_spacing = float(np.median(np.abs(deltas[non_zero])))
        else:
            slice_spacing = float(getattr(sorted_slices[0], "SliceThickness", 1.0))
    else:
        slice_spacing = float(getattr(sorted_slices[0], "SliceThickness", 1.0))
    if slice_spacing <= 0:
        slice_spacing = 1.0

    origin = np.asarray(sorted_slices[0].ImagePositionPatient, dtype=float)
    rows = int(getattr(sorted_slices[0], "Rows", 0))
    cols = int(getattr(sorted_slices[0], "Columns", 0))
    if rows <= 0 or cols <= 0:
        raise ValueError("Referenced images have invalid Rows/Columns.")

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


def _find_ct_anchor(frame_uid: str):
    ct_candidates = [obj for obj in bpy.data.objects if bool(obj.get("medblend_is_ct"))]
    if frame_uid:
        ct_candidates = [obj for obj in ct_candidates if obj.get("medblend_frame_of_reference_uid", "") == frame_uid]
    if not ct_candidates:
        return None
    return ct_candidates[-1]


def _set_object_patient_transform(obj, origin_mm, slice_dir, row_dir, col_dir) -> None:
    rot = Matrix(
        (
            (float(slice_dir[0]), float(row_dir[0]), float(col_dir[0]), 0.0),
            (float(slice_dir[1]), float(row_dir[1]), float(col_dir[1]), 0.0),
            (float(slice_dir[2]), float(row_dir[2]), float(col_dir[2]), 0.0),
            (0.0, 0.0, 0.0, 1.0),
        )
    )
    rot.translation = (
        float(origin_mm[0]) / 1000.0,
        float(origin_mm[1]) / 1000.0,
        float(origin_mm[2]) / 1000.0,
    )
    obj.matrix_world = rot


def _polygon_mask(shape: tuple[int, int], polygon_rc: np.ndarray) -> np.ndarray:
    rows, cols = shape
    if polygon_rc.shape[0] < 3:
        return np.zeros(shape, dtype=bool)

    poly_r = polygon_rc[:, 0]
    poly_c = polygon_rc[:, 1]

    min_r = max(int(np.floor(np.min(poly_r))), 0)
    max_r = min(int(np.ceil(np.max(poly_r))), rows - 1)
    min_c = max(int(np.floor(np.min(poly_c))), 0)
    max_c = min(int(np.ceil(np.max(poly_c))), cols - 1)
    if min_r > max_r or min_c > max_c:
        return np.zeros(shape, dtype=bool)

    rr, cc = np.mgrid[min_r : max_r + 1, min_c : max_c + 1]
    y = rr + 0.5
    x = cc + 0.5

    inside = np.zeros_like(y, dtype=bool)
    y1 = poly_r
    x1 = poly_c
    y2 = np.roll(poly_r, -1)
    x2 = np.roll(poly_c, -1)

    for edge_index in range(len(poly_r)):
        yi, yj = y1[edge_index], y2[edge_index]
        xi, xj = x1[edge_index], x2[edge_index]
        if yi == yj:
            continue
        intersects = ((yi > y) != (yj > y))
        x_intersection = (xj - xi) * (y - yi) / (yj - yi) + xi
        inside ^= intersects & (x < x_intersection)

    mask = np.zeros(shape, dtype=bool)
    mask[min_r : max_r + 1, min_c : max_c + 1] = inside
    return mask


def _contour_points_to_ijk(points_xyz: np.ndarray, origin: np.ndarray, inv_basis: np.ndarray) -> np.ndarray:
    diffs = points_xyz - origin
    return (inv_basis @ diffs.T).T


def _rtstruct_to_masks(dicom_structure: pydicom.Dataset, geometry) -> tuple[list[np.ndarray], list[str]]:
    roi_names = {}
    for roi in getattr(dicom_structure, "StructureSetROISequence", []):
        roi_number = int(getattr(roi, "ROINumber", -1))
        roi_name = str(getattr(roi, "ROIName", f"ROI_{roi_number}"))
        roi_names[roi_number] = roi_name

    rows = geometry["rows"]
    cols = geometry["cols"]
    num_slices = geometry["num_slices"]
    origin = geometry["origin"]
    inv_basis = geometry["inv_basis"]

    struct_masks: list[np.ndarray] = []
    struct_names: list[str] = []

    for roi_contour in getattr(dicom_structure, "ROIContourSequence", []):
        roi_number = int(getattr(roi_contour, "ReferencedROINumber", -1))
        roi_name = roi_names.get(roi_number, f"ROI_{roi_number}")
        volume_mask = np.zeros((num_slices, rows, cols), dtype=bool)

        for contour in getattr(roi_contour, "ContourSequence", []):
            contour_data = getattr(contour, "ContourData", None)
            if not contour_data or len(contour_data) < 9:
                continue

            points_xyz = np.asarray(contour_data, dtype=float).reshape((-1, 3))
            ijk = _contour_points_to_ijk(points_xyz, origin, inv_basis)

            slice_index = int(np.rint(np.mean(ijk[:, 2])))
            if slice_index < 0 or slice_index >= num_slices:
                continue

            polygon_rc = ijk[:, :2]
            polygon_mask = _polygon_mask((rows, cols), polygon_rc)

            # XOR composition matches typical RTSTRUCT contour hole semantics.
            volume_mask[slice_index] ^= polygon_mask

        if np.any(volume_mask):
            struct_masks.append(volume_mask.astype(float))
            struct_names.append(roi_name)

    return struct_masks, struct_names


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
        struct_masks, struct_names = _rtstruct_to_masks(dicom_structure, geometry)
    except Exception as exc:
        show_message_box(
            f"Unable to convert RT Structure contours: {exc}",
            "Error",
            "ERROR",
        )
        return False

    if not struct_masks:
        show_message_box("No contour masks were generated from this RT Structure Set.", "Error", "ERROR")
        return False

    spacing = geometry["spacing"]
    frame_uid = _get_structure_frame_uid(dicom_structure)
    ct_anchor = _find_ct_anchor(frame_uid)
    for mask, name in zip(struct_masks, struct_names):
        result = write_vdb_volume(mask.astype(float), spacing, f"{name}.vdb")
        if not result:
            return False
        _output_path, imported_obj = result
        if not ct_anchor:
            _set_object_patient_transform(
                imported_obj,
                geometry["origin"],
                geometry["slice_axis_dir"],
                geometry["row_axis_dir"],
                geometry["col_axis_dir"],
            )
        apply_dicom_shader("Structure Material")

    return True
