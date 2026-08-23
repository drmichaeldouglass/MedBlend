"""Tests for DICOM parsing, coercion and volume extraction helpers."""

from __future__ import annotations

import numpy as np
import pytest
from pydicom.dataset import Dataset

from MedBlend.dicom_util import (
    check_dicom_image_type,
    extract_dicom_data,
    float_or,
    is_dose_file,
    is_structure_file,
    load_dicom_series,
    positive_float_or,
    rescale_dicom_image,
    sort_slices_spatially,
)

from helpers import make_slice, write_slice


class TestFloatCoercion:
    @pytest.mark.parametrize(
        "value,expected",
        [(None, 7.0), ("", 7.0), ("abc", 7.0), (3, 3.0), ("2.5", 2.5), (-1.0, -1.0)],
    )
    def test_float_or(self, value, expected):
        # DICOM Type 2 tags are often present but empty; float(None) would raise.
        assert float_or(value, 7.0) == expected

    @pytest.mark.parametrize("value", [None, "", 0, -3.0, float("nan"), float("inf")])
    def test_positive_float_or_rejects_unusable(self, value):
        assert positive_float_or(value, 1.0) == 1.0

    def test_positive_float_or_keeps_valid(self):
        assert positive_float_or("2.5", 1.0) == 2.5


class TestModalityChecks:
    def test_modality_predicates(self):
        for modality, dose, struct, image in [
            ("RTDOSE", True, False, False),
            ("RTSTRUCT", False, True, False),
            ("CT", False, False, True),
            ("MR", False, False, True),
        ]:
            ds = Dataset()
            ds.Modality = modality
            assert is_dose_file(ds) is dose
            assert is_structure_file(ds) is struct
            assert check_dicom_image_type(ds) is image

    def test_missing_modality_is_not_a_match(self):
        ds = Dataset()
        assert is_dose_file(ds) is False
        assert check_dicom_image_type(ds) is False


class TestRescale:
    def test_maps_to_unit_range_and_reports_source_range(self):
        array = np.array([[-1024.0, 0.0, 3000.0]], dtype=np.float32)
        scaled, low, high = rescale_dicom_image(array)
        assert (low, high) == (-1024.0, 3000.0)
        assert scaled.min() == pytest.approx(0.0)
        assert scaled.max() == pytest.approx(1.0)
        # The reported range must invert the normalisation exactly.
        assert np.allclose(scaled * (high - low) + low, array, atol=1e-3)

    def test_constant_volume_stays_float32(self):
        scaled, low, high = rescale_dicom_image(np.full((2, 2), 5.0, dtype=np.float32))
        assert scaled.dtype == np.float32
        assert not scaled.any()
        assert (low, high) == (5.0, 5.0)

    def test_output_is_float32_for_float64_input(self):
        scaled, _, _ = rescale_dicom_image(np.arange(6, dtype=np.float64).reshape(2, 3))
        assert scaled.dtype == np.float32


class TestSorting:
    def test_sorts_along_slice_normal_not_instance_number(self):
        slices = [make_slice(z, instance=i) for i, z in enumerate([10.0, 0.0, 5.0])]
        ordered = sort_slices_spatially(slices)
        assert [float(s.ImagePositionPatient[2]) for s in ordered] == [0.0, 5.0, 10.0]

    def test_falls_back_to_instance_number_without_positions(self):
        slices = []
        for instance in [2, 0, 1]:
            ds = make_slice(0.0, instance=instance)
            del ds.ImagePositionPatient
            slices.append(ds)
        assert [s.InstanceNumber for s in sort_slices_spatially(slices)] == [0, 1, 2]

    def test_duplicate_positions_do_not_raise(self):
        # sorted(zip(...)) would compare Datasets on ties without a key.
        slices = [make_slice(0.0, instance=i) for i in range(3)]
        assert len(sort_slices_spatially(slices)) == 3


class TestExtractDicomData:
    def test_origin_matches_flipped_array_start(self):
        slices = [make_slice(z, value=int(z), instance=i) for i, z in enumerate([0.0, 2.0, 4.0])]
        array, spacing, positions, slice_spacing, _origin, _orientation = extract_dicom_data(slices)

        # Axis 0 is flipped, so array[0] must be the *last* sorted slice, which
        # is what ct.py anchors the object origin to.
        assert array[0, 0, 0] == pytest.approx(-1024.0 + 4.0)
        assert float(positions[-1][2]) == pytest.approx(4.0)
        assert slice_spacing == pytest.approx(2.0)
        assert tuple(spacing) == (1.0, 1.0)
        assert array.dtype == np.float32

    def test_slice_spacing_prefers_positions_over_thickness(self):
        # SliceThickness (2.0) disagrees with the real 5 mm gap between slices.
        slices = [make_slice(z, instance=i) for i, z in enumerate([0.0, 5.0, 10.0])]
        _, _, _, slice_spacing, _, _ = extract_dicom_data(slices)
        assert slice_spacing == pytest.approx(5.0)

    def test_non_uniform_slice_positions_are_rejected(self):
        slices = [make_slice(z, instance=i) for i, z in enumerate([0.0, 3.0, 6.0, 20.0])]
        with pytest.raises(ValueError, match="slice spacing is non-uniform"):
            extract_dicom_data(slices)

    def test_mismatched_matrix_size_names_the_offending_slice(self):
        slices = [make_slice(0.0, instance=0), make_slice(2.0, rows=4, cols=4, instance=1)]
        with pytest.raises(ValueError, match="Slice 2 is 4x4"):
            extract_dicom_data(slices)

    def test_empty_input_raises(self):
        with pytest.raises(ValueError, match="No DICOM images"):
            extract_dicom_data([])

    def test_missing_pixel_spacing_defaults_to_one(self):
        ds = make_slice(0.0)
        ds.PixelSpacing = None
        _, spacing, _, _, _, _ = extract_dicom_data([ds])
        assert tuple(spacing) == (1.0, 1.0)


class TestLoadDicomSeries:
    def test_filters_by_series_and_skips_duplicates(self, tmp_path):
        write_slice(tmp_path, make_slice(0.0, instance=0), "a.dcm")
        write_slice(tmp_path, make_slice(2.0, instance=1), "b.dcm")
        # Same SOPInstanceUID as a.dcm: a copied file must not be stacked twice.
        write_slice(tmp_path, make_slice(0.0, instance=0), "a copy.dcm")

        other_series = make_slice(0.0, instance=9)
        other_series.SeriesInstanceUID = "9.9.9"
        write_slice(tmp_path, other_series, "other.dcm")

        (tmp_path / "notes.txt").write_text("not dicom")

        loaded = load_dicom_series(tmp_path, "1.2.3")
        assert len(loaded) == 2
        assert {str(ds.SOPInstanceUID) for ds in loaded} == {"1.2.3.0", "1.2.3.1"}

    def test_unknown_series_returns_empty(self, tmp_path):
        write_slice(tmp_path, make_slice(0.0, instance=0), "a.dcm")
        assert load_dicom_series(tmp_path, "does.not.exist") == []
