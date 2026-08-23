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


def rescale_dicom_image(array: np.ndarray) -> Tuple[np.ndarray, float, float]:
    """Scale the array into ``[0, 1]`` and report the source intensity range.

    The original min/max are returned so callers can record the mapping back
    to Hounsfield units, which the normalisation would otherwise discard.
    """

    array = np.asarray(array, dtype=np.float32)
    min_value = float(np.min(array))
    max_value = float(np.max(array))
    if max_value == min_value:
        return np.zeros_like(array, dtype=np.float32), min_value, max_value

    scaled = (array - min_value) / (max_value - min_value)
    return np.asarray(scaled, dtype=np.float32), min_value, max_value


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
    orientation = np.asarray(getattr(ds, "ImageOrientationPatient", []), dtype=float)
    if orientation.size != 6:
        return None
    normal = np.cross(orientation[:3], orientation[3:])
    norm = float(np.linalg.norm(normal))
    if norm <= 0:
        return None
    return normal / norm


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

    return [ds for _, ds in sorted(zip(projections, images), key=lambda pair: pair[0])]


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


def extract_dicom_data(
    images: Sequence[pydicom.Dataset],
) -> Tuple[np.ndarray, Sequence[float], Sequence[float], float, Sequence[float], Sequence[float]]:
    """Extract voxel data and metadata from the provided DICOM slices."""

    if not images:
        raise ValueError("No DICOM images were provided for extraction")

    expected_shape = None
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

        # Apply the modality LUT per slice: RescaleSlope/Intercept may differ
        # between slices, in which case raw stored values are not comparable.
        slope = float_or(getattr(dataset, "RescaleSlope", 1.0), 1.0)
        intercept = float_or(getattr(dataset, "RescaleIntercept", 0.0), 0.0)
        if slope != 1.0 or intercept != 0.0:
            pixels = pixels * np.float32(slope) + np.float32(intercept)
        dicom_3d_array.append(pixels)
        slice_positions.append(getattr(dataset, "ImagePositionPatient", (0.0, 0.0, 0.0)))

    array = np.asarray(dicom_3d_array, dtype=np.float32)
    array = np.flipud(array)

    first = images[0]
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
