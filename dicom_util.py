"""Utility helpers for reading and validating DICOM data."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Sequence, Tuple
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


def load_dicom_images(folder: Path) -> List[pydicom.Dataset]:
    """Load all CT/MR DICOM files within ``folder``."""

    images: List[pydicom.Dataset] = []
    for file_path in folder.iterdir():
        if file_path.suffix.lower() != ".dcm":
            continue

        try:
            image = pydicom.dcmread(file_path)
        except Exception:
            continue

        if image and check_dicom_image_type(image):
            images.append(image)

    return images


def rescale_dicom_image(array: np.ndarray) -> np.ndarray:
    """Scale the array into the range ``[0, 1]``."""

    import numpy as np

    min_value = float(np.min(array))
    max_value = float(np.max(array))
    if max_value == min_value:
        return np.zeros_like(array, dtype=float)

    return (array - min_value) / (max_value - min_value)


def sort_by_instance_number(images: Iterable[pydicom.Dataset]) -> List[pydicom.Dataset]:
    """Return the images sorted by ``InstanceNumber``."""

    return sorted(images, key=lambda x: getattr(x, "InstanceNumber", 0))


def extract_dicom_data(
    images: Sequence[pydicom.Dataset],
) -> Tuple[np.ndarray, Sequence[float], Sequence[float], float, Sequence[float], Sequence[float], int]:
    """Extract voxel data and metadata from the provided DICOM slices."""

    import numpy as np

    if not images:
        raise ValueError("No DICOM images were provided for extraction")

    dicom_3d_array = []
    slice_positions = []
    for dataset in images:
        dicom_3d_array.append(dataset.pixel_array)
        slice_positions.append(getattr(dataset, "ImagePositionPatient", (0.0, 0.0, 0.0)))

    array = np.asarray(dicom_3d_array)
    array = np.flipud(array)

    first = images[0]
    spacing = getattr(first, "PixelSpacing", (1.0, 1.0))
    slice_thickness = getattr(first, "SliceThickness", 1.0)
    image_origin = getattr(first, "ImagePositionPatient", (0.0, 0.0, 0.0))
    image_orientation = getattr(first, "ImageOrientationPatient", (0.0,) * 6)
    image_columns = getattr(first, "Columns", 0)

    return (
        array,
        spacing,
        slice_positions,
        slice_thickness,
        image_origin,
        image_orientation,
        image_columns,
    )


def filter_by_series_uid(images: Iterable[pydicom.Dataset], series_uid: str) -> List[pydicom.Dataset]:
    """Return the images that match the requested ``SeriesInstanceUID``."""

    return [image for image in images if getattr(image, "SeriesInstanceUID", None) == series_uid]

