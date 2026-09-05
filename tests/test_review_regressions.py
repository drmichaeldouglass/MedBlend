"""Regressions for slice shear, modality LUTs, and portable VDB names."""

import numpy as np
import pytest
from pydicom.dataset import Dataset

from MedBlend import ct
from MedBlend.dicom_util import extract_dicom_data
from MedBlend.structure import _build_geometry
from MedBlend.volume_utils import _sanitize_filename, _unique_path
from helpers import make_slice


def shifted_slices():
    slices = [make_slice(2 * i, instance=i) for i in range(4)]
    for i, ds in enumerate(slices):
        ds.ImagePositionPatient = [100 + i * 0.5, 20 - i * 0.25, 2 * i]
    return slices


def test_ct_rejects_sheared_stack_before_writing(monkeypatch, tmp_path):
    slices = shifted_slices()
    monkeypatch.setattr(ct.pydicom, "dcmread", lambda *a, **kw: slices[0])
    monkeypatch.setattr(ct, "load_dicom_series", lambda *a: slices)
    writes = []
    monkeypatch.setattr(ct, "write_vdb_volume", lambda *a: writes.append(a))
    messages = []
    monkeypatch.setattr(ct, "show_message_box", lambda *a: messages.append(a))

    assert ct.load_ct_series(tmp_path / "slice.dcm") is False
    assert not writes
    assert "sheared stack" in messages[0][0]


def test_structure_grid_rejects_sheared_stack():
    slices = shifted_slices()
    with pytest.raises(ValueError, match="sheared stack"):
        _build_geometry(list(reversed(slices)))


@pytest.mark.parametrize("builder", [extract_dicom_data, _build_geometry])
def test_nonuniform_sideways_displacement_is_rejected(builder):
    slices = shifted_slices()
    slices[1].ImagePositionPatient[0] += 0.2
    with pytest.raises(ValueError, match="in-plane displacement"):
        builder(slices)


@pytest.mark.parametrize("builder", [extract_dicom_data, _build_geometry])
def test_oblique_orthogonal_stack_is_still_supported(builder):
    slices = [make_slice(0, instance=i) for i in range(4)]
    for i, ds in enumerate(slices):
        ds.ImageOrientationPatient = [1, 0, 0, 0, 0.8, 0.6]
        ds.ImagePositionPatient = [100, 20 - i * 1.2, i * 1.6]
    builder(slices)


def test_modality_lut_applies_before_float_conversion_and_rescale():
    ds = make_slice(0)
    ds.PixelData = np.asarray([[-2, -1], [0, 5]], dtype=np.int16).tobytes()
    lut = Dataset()
    lut.LUTDescriptor = [3, -1, 16]
    lut.ModalityLUTType = "US"
    lut.LUTData = [100, 300, 900]
    ds.ModalityLUTSequence = [lut]
    # LUT wins when rescale tags are also present; out-of-range values clamp.
    ds.RescaleSlope = 2
    ds.RescaleIntercept = -1024
    second = make_slice(2, value=10, instance=1)
    array, *_ = extract_dicom_data([ds, second])
    assert array.dtype == np.float32
    np.testing.assert_array_equal(array[1], [[100, 100], [300, 900]])
    np.testing.assert_array_equal(array[0], np.full((2, 2), -1014))


def test_malformed_modality_lut_reports_the_slice():
    ds = make_slice(0)
    ds.ModalityLUTSequence = [Dataset()]
    with pytest.raises(ValueError, match="Slice 1 has an invalid ModalityLUTSequence"):
        extract_dicom_data([ds])


@pytest.mark.parametrize("character", ["骨", "é", "𐐀"])
def test_unicode_roi_filename_can_be_written_and_reused(tmp_path, character):
    name = _sanitize_filename(character * 120 + ".vdb")
    path = _unique_path(tmp_path, name)
    path.write_bytes(b"first volume")
    second = _unique_path(tmp_path, name)
    second.write_bytes(b"second volume")
    assert path != second
    assert path.read_bytes() == b"first volume"
    assert second.suffix == ".vdb"


@pytest.mark.parametrize("name", ["CON.backup.vdb", "aux.test.vdb", "LPT1.extra.vdb"])
def test_windows_device_names_with_multiple_extensions_are_sanitised(name):
    result = _sanitize_filename(name)
    assert result.split(".", 1)[0].upper() not in {"CON", "AUX", "LPT1"}
    assert result.endswith(".vdb")
