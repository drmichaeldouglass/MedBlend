"""Helper functions for working with DICOM data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, List, Sequence

if TYPE_CHECKING:  # pragma: no cover - typing support without runtime dependency
    import numpy as np


@dataclass
class VolumeData:
    """Represents a volumetric DICOM dataset."""

    array: "np.ndarray"
    pixel_spacing: Sequence[float]
    slice_thickness: float
    origin: Sequence[float]
    orientation: Sequence[float]
    slice_positions: List[Sequence[float]]


def is_dose(dataset: Any) -> bool:
    return getattr(dataset, "Modality", "").upper() == "RTDOSE"


def is_structure(dataset: Any) -> bool:
    return getattr(dataset, "Modality", "").upper() == "RTSTRUCT"


def is_image(dataset: Any) -> bool:
    modality = getattr(dataset, "Modality", "").upper()
    return modality in {"CT", "MR"}


def load_image_series(directory: Path, *, pydicom: Any, series_uid: str | None = None) -> list[Any]:
    """Return a list of DICOM slices belonging to *series_uid* in *directory*."""

    images: list[Any] = []
    for path in sorted(directory.glob("*.dcm")):
        try:
            dataset = pydicom.dcmread(str(path))
        except Exception:
            continue

        if series_uid is not None and getattr(dataset, "SeriesInstanceUID", None) != series_uid:
            continue
        if not is_image(dataset):
            continue
        images.append(dataset)
    images.sort(key=lambda ds: getattr(ds, "InstanceNumber", 0))
    return images


def build_volume(images: Iterable[Any], *, numpy: Any) -> VolumeData | None:
    """Create a :class:`VolumeData` from *images* using *numpy* for array handling."""

    images = list(images)
    if not images:
        return None

    pixel_arrays = []
    slice_positions: List[Sequence[float]] = []
    for dataset in images:
        try:
            pixel_arrays.append(dataset.pixel_array)
        except Exception:
            return None
        slice_positions.append(getattr(dataset, "ImagePositionPatient", (0.0, 0.0, 0.0)))

    volume = numpy.stack(pixel_arrays, axis=0)
    volume = numpy.flip(volume, axis=0)

    first = images[0]
    spacing = _as_float_sequence(getattr(first, "PixelSpacing", (1.0, 1.0)))
    slice_thickness = float(getattr(first, "SliceThickness", 1.0))
    origin = _as_float_sequence(getattr(first, "ImagePositionPatient", (0.0, 0.0, 0.0)))
    orientation = _as_float_sequence(getattr(first, "ImageOrientationPatient", (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)))

    return VolumeData(
        array=volume,
        pixel_spacing=spacing,
        slice_thickness=slice_thickness,
        origin=origin,
        orientation=orientation,
        slice_positions=slice_positions,
    )


def _as_float_sequence(values: Iterable[Any]) -> list[float]:
    return [float(v) for v in values]


__all__ = [
    "VolumeData",
    "build_volume",
    "is_dose",
    "is_image",
    "is_structure",
    "load_image_series",
]
