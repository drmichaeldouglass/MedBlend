"""Utility helpers for reading and validating DICOM data."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

import numpy as np
import pydicom


def is_dose_file(ds: pydicom.Dataset) -> bool:
    """Return ``True`` when the dataset represents a dose file."""

    try:
        return ds.Modality == "RTDOSE"
    except Exception:
        return False


def is_structure_file(ds: pydicom.Dataset) -> bool:
    """Return ``True`` when the dataset represents an RT structure file."""

    try:
        return ds.Modality == "RTSTRUCT"
    except Exception:
        return False


def check_dicom_image_type(ds: pydicom.Dataset) -> bool:
    """Check whether the dataset represents a CT or MR image."""

    try:
        return ds.Modality in {"CT", "MR"}
    except Exception:
        return False


def load_dicom_series(folder: Path, series_uid: str) -> List[pydicom.Dataset]:
    """Load the CT/MR files in ``folder`` that belong to ``series_uid``.

    Scans headers only (``stop_before_pixels``) first, so pixel data is read
    and decoded just for the slices of the requested series rather than for
    every file in the directory.
    """

    matching_paths: List[Path] = []
    seen_sop_uids: set[str] = set()
    for file_path in sorted(folder.iterdir()):
        if not file_path.is_file():
            continue
        try:
            header = pydicom.dcmread(file_path, stop_before_pixels=True)
        except Exception:
            continue
        if not check_dicom_image_type(header):
            continue
        if getattr(header, "SeriesInstanceUID", None) != series_uid:
            continue
        # Copies of the same slice (``IMG1.dcm`` and ``IMG1 (1).dcm``) would
        # otherwise be stacked twice and double the apparent slice count.
        sop_uid = str(getattr(header, "SOPInstanceUID", ""))
        if sop_uid:
            if sop_uid in seen_sop_uids:
                continue
            seen_sop_uids.add(sop_uid)
        matching_paths.append(file_path)

    images: List[pydicom.Dataset] = []
    for file_path in matching_paths:
        try:
            images.append(pydicom.dcmread(file_path))
        except Exception:
            continue
    return images


def image_intensity_range(array: np.ndarray) -> Tuple[np.ndarray, float, float]:
    """Validate voxel intensities and report the range they occupy.

    The values are passed through untouched, so a CT keeps the Hounsfield
    units the modality LUT produced and a voxel sampled in Blender reads the
    same number as the DICOM file. Only the dtype is narrowed to ``float32``,
    which is what OpenVDB's ``FloatGrid`` stores anyway.

    The min/max are returned for the shader: a transfer function still has to
    be windowed onto the range a particular scan occupies.
    """

    array = np.asarray(array, dtype=np.float32)
    if array.size == 0:
        raise ValueError("DICOM image data is empty")
    if not np.all(np.isfinite(array)):
        raise ValueError("DICOM image data contains non-finite intensity values")

    return array, float(np.min(array)), float(np.max(array))


def _instance_number_key(ds: pydicom.Dataset) -> int:
    value = getattr(ds, "InstanceNumber", None)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def sort_by_instance_number(images: Iterable[pydicom.Dataset]) -> List[pydicom.Dataset]:
    """Return the images sorted by ``InstanceNumber``."""

    return sorted(images, key=_instance_number_key)


def _slice_normal(ds: pydicom.Dataset) -> np.ndarray | None:
    try:
        _row_dir, _col_dir, normal = image_orientation_axes(
            getattr(ds, "ImageOrientationPatient", None)
        )
    except ValueError:
        return None
    return normal


def image_orientation_axes(
    image_orientation,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return normalised row, column, and slice axes from DICOM orientation."""

    try:
        orientation = np.asarray(image_orientation, dtype=float).reshape(-1)
    except (TypeError, ValueError) as exc:
        raise ValueError("ImageOrientationPatient must contain six numeric values") from exc
    if orientation.size != 6 or not np.all(np.isfinite(orientation)):
        raise ValueError("ImageOrientationPatient must contain six finite values")

    row_dir = orientation[:3]
    col_dir = orientation[3:]
    row_norm = float(np.linalg.norm(row_dir))
    col_norm = float(np.linalg.norm(col_dir))
    if row_norm <= 1e-8 or col_norm <= 1e-8:
        raise ValueError("ImageOrientationPatient contains a zero-length direction")

    row_dir = row_dir / row_norm
    col_dir = col_dir / col_norm
    if abs(float(np.dot(row_dir, col_dir))) > 1e-4:
        raise ValueError("ImageOrientationPatient row and column directions are not orthogonal")

    normal_dir = np.cross(row_dir, col_dir)
    normal_norm = float(np.linalg.norm(normal_dir))
    if normal_norm <= 1e-8:
        raise ValueError("ImageOrientationPatient does not define a usable slice direction")
    return row_dir, col_dir, normal_dir / normal_norm


def sort_slices_spatially(images: Sequence[pydicom.Dataset]) -> List[pydicom.Dataset]:
    """Sort slices by position along the slice normal.

    ``InstanceNumber`` ordering is not guaranteed to match spatial ordering,
    so prefer sorting by the projection of ``ImagePositionPatient`` onto the
    slice normal. Falls back to ``InstanceNumber`` when positions or
    orientation are unavailable.
    """

    images = list(images)
    if len(images) < 2:
        return images

    normal = _slice_normal(images[0])
    positions = [getattr(ds, "ImagePositionPatient", None) for ds in images]
    if normal is None or any(pos is None or len(pos) != 3 for pos in positions):
        return sort_by_instance_number(images)

    projections = [float(np.dot(np.asarray(pos, dtype=float), normal)) for pos in positions]
    if max(projections) - min(projections) <= 1e-6:
        return sort_by_instance_number(images)

    return [
        ds
        for _, ds in sorted(
            zip(projections, images, strict=True), key=lambda pair: pair[0]
        )
    ]


def _compute_slice_spacing(
    slice_positions: Sequence[Sequence[float]],
    image_orientation: Sequence[float],
    fallback_thickness,
) -> float:
    """Derive slice spacing from slice positions when possible.

    ``SliceThickness`` describes the thickness of a single slice and may not
    match the actual spacing between slices (gaps or overlap), so the
    distance between consecutive ``ImagePositionPatient`` values projected
    onto the slice normal is preferred.
    """

    try:
        positions = np.asarray(slice_positions, dtype=float)
        orientation = np.asarray(image_orientation, dtype=float)
    except (TypeError, ValueError):
        positions = np.asarray([])
        orientation = np.asarray([])

    if positions.ndim == 2 and positions.shape[1] == 3 and len(positions) >= 2 and orientation.size == 6:
        normal = np.cross(orientation[:3], orientation[3:])
        norm = float(np.linalg.norm(normal))
        if norm > 0:
            projections = positions @ (normal / norm)
            deltas = np.abs(np.diff(projections))
            if not np.all(np.isfinite(deltas)) or np.any(deltas <= 1e-6):
                raise ValueError(
                    "CT/MR slices contain duplicate or invalid ImagePositionPatient values."
                )

            slice_spacing = float(np.median(deltas))
            if not np.allclose(deltas, slice_spacing, rtol=1e-4, atol=1e-3):
                positions_text = ", ".join(f"{value:.3g}" for value in deltas[:6])
                if len(deltas) > 6:
                    positions_text += ", ..."
                raise ValueError(
                    "CT/MR slice spacing is non-uniform "
                    f"({positions_text} mm). MedBlend cannot represent non-uniform "
                    "slice positions in a linearly transformed VDB volume."
                )
            return slice_spacing

    return positive_float_or(fallback_thickness, 1.0)


def float_or(value, default: float) -> float:
    """Coerce a DICOM value to ``float``, falling back to ``default``.

    Type 2 attributes such as ``SliceThickness`` are frequently present but
    empty, in which case pydicom yields ``None`` and a bare ``float()`` call
    raises ``TypeError``.
    """

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def positive_float_or(value, default: float) -> float:
    """Like :func:`float_or`, but also rejects zero, negative and NaN values."""

    result = float_or(value, default)
    if not np.isfinite(result) or result <= 0:
        return default
    return result


# Backwards-compatible private alias used elsewhere in this module.
_float_or = float_or


def _optional_numeric_vector(
    value,
    expected_length: int,
    attribute_name: str,
    slice_number: int,
) -> np.ndarray | None:
    """Coerce an optional DICOM vector and give geometry errors context."""

    if value is None:
        return None
    try:
        vector = np.asarray(value, dtype=float).reshape(-1)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Slice {slice_number} has a non-numeric {attribute_name}."
        ) from exc
    if vector.size != expected_length or not np.all(np.isfinite(vector)):
        raise ValueError(
            f"Slice {slice_number} has an invalid {attribute_name}; "
            f"expected {expected_length} finite values."
        )
    return vector


def extract_dicom_data(
    images: Sequence[pydicom.Dataset],
) -> Tuple[np.ndarray, Sequence[float], Sequence[float], float, Sequence[float], Sequence[float]]:
    """Extract voxel data and metadata from the provided DICOM slices."""

    if not images:
        raise ValueError("No DICOM images were provided for extraction")

    first = images[0]
    expected_shape = None
    reference_orientation = _optional_numeric_vector(
        getattr(first, "ImageOrientationPatient", None),
        6,
        "ImageOrientationPatient",
        1,
    )
    reference_spacing = _optional_numeric_vector(
        getattr(first, "PixelSpacing", None),
        2,
        "PixelSpacing",
        1,
    )
    dicom_3d_array = []
    slice_positions = []
    for index, dataset in enumerate(images):
        try:
            pixels = np.asarray(dataset.pixel_array, dtype=np.float32)
        except Exception as exc:
            raise ValueError(
                f"Could not decode pixel data for slice {index + 1} of {len(images)}. "
                f"The transfer syntax may be unsupported by pydicom: {exc}"
            ) from exc

        if pixels.ndim != 2:
            raise ValueError(
                f"Slice {index + 1} has {pixels.ndim} pixel dimensions; only single-frame "
                "2D CT/MR slices are supported."
            )
        # Mixed in-plane sizes cannot be stacked into one volume, and NumPy's
        # own error for a ragged stack does not say which file is at fault.
        if expected_shape is None:
            expected_shape = pixels.shape
        elif pixels.shape != expected_shape:
            raise ValueError(
                f"Slice {index + 1} is {pixels.shape[0]}x{pixels.shape[1]} but the series "
                f"starts with {expected_shape[0]}x{expected_shape[1]}. All slices in a "
                "series must share the same matrix size."
            )

        orientation = _optional_numeric_vector(
            getattr(dataset, "ImageOrientationPatient", None),
            6,
            "ImageOrientationPatient",
            index + 1,
        )
        pixel_spacing = _optional_numeric_vector(
            getattr(dataset, "PixelSpacing", None),
            2,
            "PixelSpacing",
            index + 1,
        )
        if (orientation is None) != (reference_orientation is None) or (
            orientation is not None
            and not np.allclose(orientation, reference_orientation, rtol=1e-5, atol=1e-6)
        ):
            raise ValueError(
                f"Slice {index + 1} has ImageOrientationPatient inconsistent with slice 1."
            )
        if (pixel_spacing is None) != (reference_spacing is None) or (
            pixel_spacing is not None
            and not np.allclose(pixel_spacing, reference_spacing, rtol=1e-4, atol=1e-3)
        ):
            raise ValueError(f"Slice {index + 1} has PixelSpacing inconsistent with slice 1.")

        # Apply the modality LUT per slice: RescaleSlope/Intercept may differ
        # between slices, in which case raw stored values are not comparable.
        slope = float_or(getattr(dataset, "RescaleSlope", 1.0), 1.0)
        intercept = float_or(getattr(dataset, "RescaleIntercept", 0.0), 0.0)
        if not np.isfinite(slope) or not np.isfinite(intercept):
            raise ValueError(
                f"Slice {index + 1} has a non-finite RescaleSlope or RescaleIntercept."
            )
        if slope != 1.0 or intercept != 0.0:
            pixels = pixels * np.float32(slope) + np.float32(intercept)
        if not np.all(np.isfinite(pixels)):
            raise ValueError(f"Slice {index + 1} contains non-finite intensity values.")
        dicom_3d_array.append(pixels)
        raw_position = getattr(dataset, "ImagePositionPatient", None)
        if raw_position is None:
            slice_positions.append((0.0, 0.0, 0.0))
        else:
            slice_positions.append(
                _optional_numeric_vector(
                    raw_position,
                    3,
                    "ImagePositionPatient",
                    index + 1,
                )
            )

    array = np.asarray(dicom_3d_array, dtype=np.float32)
    array = np.flipud(array)

    spacing = getattr(first, "PixelSpacing", (1.0, 1.0))
    if spacing is None or len(spacing) < 2:
        spacing = (1.0, 1.0)
    spacing = (positive_float_or(spacing[0], 1.0), positive_float_or(spacing[1], 1.0))
    image_origin = getattr(first, "ImagePositionPatient", (0.0, 0.0, 0.0))
    image_orientation = getattr(first, "ImageOrientationPatient", (0.0,) * 6)
    slice_spacing = _compute_slice_spacing(
        slice_positions,
        image_orientation,
        getattr(first, "SliceThickness", 1.0),
    )

    return (
        array,
        spacing,
        slice_positions,
        slice_spacing,
        image_origin,
        image_orientation,
    )
