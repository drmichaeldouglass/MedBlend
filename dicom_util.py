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
        matching_paths.append(file_path)

    images: List[pydicom.Dataset] = []
    for file_path in matching_paths:
        try:
            images.append(pydicom.dcmread(file_path))
        except Exception:
            continue
    return images


def rescale_dicom_image(array: np.ndarray) -> np.ndarray:
    """Scale the array into the range ``[0, 1]``."""

    min_value = float(np.min(array))
    max_value = float(np.max(array))
    if max_value == min_value:
        return np.zeros_like(array, dtype=float)

    return (array - min_value) / (max_value - min_value)


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
        if positions.ndim == 2 and positions.shape[1] == 3 and len(positions) >= 2 and orientation.size == 6:
            normal = np.cross(orientation[:3], orientation[3:])
            norm = float(np.linalg.norm(normal))
            if norm > 0:
                projections = positions @ (normal / norm)
                deltas = np.diff(projections)
                non_zero = np.abs(deltas) > 1e-6
                if np.any(non_zero):
                    return float(np.median(np.abs(deltas[non_zero])))
    except Exception:
        pass

    try:
        spacing = float(fallback_thickness)
    except (TypeError, ValueError):
        spacing = 0.0
    return spacing if spacing > 0 else 1.0


def _float_or(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def extract_dicom_data(
    images: Sequence[pydicom.Dataset],
) -> Tuple[np.ndarray, Sequence[float], Sequence[float], float, Sequence[float], Sequence[float]]:
    """Extract voxel data and metadata from the provided DICOM slices."""

    if not images:
        raise ValueError("No DICOM images were provided for extraction")

    dicom_3d_array = []
    slice_positions = []
    for dataset in images:
        pixels = np.asarray(dataset.pixel_array, dtype=np.float32)
        # Apply the modality LUT per slice: RescaleSlope/Intercept may differ
        # between slices, in which case raw stored values are not comparable.
        slope = _float_or(getattr(dataset, "RescaleSlope", 1.0), 1.0)
        intercept = _float_or(getattr(dataset, "RescaleIntercept", 0.0), 0.0)
        if slope != 1.0 or intercept != 0.0:
            pixels = pixels * slope + intercept
        dicom_3d_array.append(pixels)
        slice_positions.append(getattr(dataset, "ImagePositionPatient", (0.0, 0.0, 0.0)))

    array = np.asarray(dicom_3d_array)
    array = np.flipud(array)

    first = images[0]
    spacing = getattr(first, "PixelSpacing", (1.0, 1.0))
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
