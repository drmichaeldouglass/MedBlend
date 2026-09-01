"""Tests that a volume which cannot be placed in patient space says so.

The voxels are already imported by the time the transform is built, so a
failure there must not discard the volume - but it must not pass silently
either, because dose, structures and plans all co-register through it.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pydicom
import pytest
from pydicom.dataset import Dataset, FileMetaDataset

from MedBlend import ct as ct_module
from MedBlend import dose as dose_module
from helpers import make_slice, write_slice


class FakeVolumeObject:
    type = "VOLUME"

    def __init__(self, name="CT"):
        self.name = name
        self.matrix_world = None
        self._properties = {}

    def get(self, key, default=None):
        return self._properties.get(key, default)

    def __setitem__(self, key, value):
        self._properties[key] = value

    def __getitem__(self, key):
        return self._properties[key]


@pytest.fixture
def captured(monkeypatch):
    """Collect messages from both loaders instead of popping dialogs."""

    messages = []

    def record(message="", title="Message", icon="INFO"):
        messages.append((title, str(message)))

    for module in (ct_module, dose_module):
        monkeypatch.setattr(module, "show_message_box", record)
    return messages


@pytest.fixture
def stub_volume_writer(monkeypatch):
    """Make write_vdb_volume hand back an object without touching OpenVDB."""

    created = []

    def fake_write(_array, _spacing, target_name, on_error=None):
        obj = FakeVolumeObject(Path(target_name).stem)
        created.append(obj)
        return Path(target_name), obj

    for module in (ct_module, dose_module):
        monkeypatch.setattr(module, "write_vdb_volume", fake_write)
        monkeypatch.setattr(module, "apply_dicom_shader", lambda *a, **k: True)
    monkeypatch.setattr(ct_module, "apply_volume_preset", lambda *a, **k: None)
    return created


def write_ct_series(folder, orientation, count=3):
    for index in range(count):
        slice_ds = make_slice(index * 2.0, value=100 * index, instance=index)
        slice_ds.ImageOrientationPatient = list(orientation)
        slice_ds.FrameOfReferenceUID = "1.2.frame"
        write_slice(folder, slice_ds, f"slice{index}.dcm")
    return folder / "slice0.dcm"


class TestCtPlacementReporting:
    def test_a_well_formed_series_reports_nothing(self, tmp_path, captured, stub_volume_writer):
        selected = write_ct_series(tmp_path, [1, 0, 0, 0, 1, 0])
        assert ct_module.load_ct_series(selected) is True
        assert captured == []
        assert stub_volume_writer[0].matrix_world is not None

    def test_degenerate_orientation_warns_but_keeps_the_volume(
        self, tmp_path, captured, stub_volume_writer
    ):
        selected = write_ct_series(tmp_path, [0, 0, 0, 0, 0, 0])

        # The import still succeeds - the voxels are fine, only the placement
        # is not - but the user is told the scene will not co-register.
        assert ct_module.load_ct_series(selected) is True
        assert len(captured) == 1
        title, message = captured[0]
        assert title == "Warning"
        assert "could not be placed" in message
        assert "co-register" in message

    def test_the_import_index_is_recorded_for_later_alignment(
        self, tmp_path, captured, stub_volume_writer
    ):
        selected = write_ct_series(tmp_path, [1, 0, 0, 0, 1, 0])
        ct_module.load_ct_series(selected)
        assert stub_volume_writer[0].get(ct_module.CT_IMPORT_INDEX_KEY) == 1


def make_dose_dataset(tmp_path, orientation):
    ds = Dataset()
    ds.Modality = "RTDOSE"
    ds.SOPClassUID = pydicom.uid.RTDoseStorage
    ds.SOPInstanceUID = "1.2.dose"
    ds.FrameOfReferenceUID = "1.2.frame"
    ds.ImagePositionPatient = [0.0, 0.0, 0.0]
    ds.ImageOrientationPatient = list(orientation)
    ds.PixelSpacing = [2.0, 2.0]
    ds.GridFrameOffsetVector = [0.0, 3.0]
    ds.DoseGridScaling = 0.01
    ds.DoseUnits = "GY"
    ds.NumberOfFrames = 2
    ds.Rows, ds.Columns = 2, 2
    ds.BitsAllocated, ds.BitsStored, ds.HighBit = 16, 16, 15
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.PixelRepresentation = 0
    ds.PixelData = np.arange(2 * 2 * 2, dtype=np.uint16).tobytes()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = ds.SOPClassUID
    ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    path = tmp_path / "dose.dcm"
    pydicom.dcmwrite(path, ds, enforce_file_format=True)
    return path


class TestDosePlacementReporting:
    def test_a_well_formed_dose_reports_nothing(self, tmp_path, captured, stub_volume_writer):
        path = make_dose_dataset(tmp_path, [1, 0, 0, 0, 1, 0])
        assert dose_module.load_dose(path) is True
        assert captured == []
        assert stub_volume_writer[0].matrix_world is not None

    def test_a_placement_failure_is_reported(
        self, tmp_path, captured, stub_volume_writer, monkeypatch
    ):
        path = make_dose_dataset(tmp_path, [1, 0, 0, 0, 1, 0])

        def explode(*_args, **_kwargs):
            raise ValueError("orientation is not invertible")

        monkeypatch.setattr(dose_module, "set_object_patient_transform", explode)
        monkeypatch.setattr(dose_module, "find_ct_anchor", lambda _uid: None)

        assert dose_module.load_dose(path) is True
        assert len(captured) == 1
        title, message = captured[0]
        assert title == "Warning"
        assert "orientation is not invertible" in message
        # The dose metadata is still written, so the volume stays usable.
        assert stub_volume_writer[0].get("medblend_dose_units") == "GY"
