"""Shared DICOM fixtures for the MedBlend test suite."""

from __future__ import annotations

import numpy as np
import pydicom
from pydicom.dataset import Dataset, FileMetaDataset


def make_slice(
    z: float,
    *,
    value: int = 0,
    rows: int = 2,
    cols: int = 2,
    instance: int = 0,
    series_uid: str = "1.2.3",
) -> Dataset:
    """A minimal but decodable axial CT slice at patient position ``z``."""

    ds = Dataset()
    ds.Modality = "CT"
    ds.SeriesInstanceUID = series_uid
    ds.SOPInstanceUID = f"{series_uid}.{instance}"
    ds.InstanceNumber = instance
    ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    ds.ImagePositionPatient = [0.0, 0.0, z]
    ds.PixelSpacing = [1.0, 1.0]
    ds.SliceThickness = 2.0
    ds.RescaleSlope = 1.0
    ds.RescaleIntercept = -1024.0
    ds.Rows, ds.Columns = rows, cols
    ds.BitsAllocated, ds.BitsStored, ds.HighBit = 16, 16, 15
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.PixelRepresentation = 1
    ds.PixelData = np.full((rows, cols), value, dtype=np.int16).tobytes()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
    return ds


def write_slice(folder, ds: Dataset, name: str):
    """Write ``ds`` to ``folder/name`` as a conformant Part 10 file."""

    path = folder / name
    ds.SOPClassUID = pydicom.uid.CTImageStorage
    ds.file_meta.MediaStorageSOPClassUID = ds.SOPClassUID
    ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    pydicom.dcmwrite(path, ds, enforce_file_format=True)
    return path
