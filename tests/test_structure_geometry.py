"""Tests for RT structure rasterisation and the mask cropping geometry."""

from __future__ import annotations

import numpy as np
import pytest
from pydicom.dataelem import RawDataElement
from pydicom.dataset import Dataset
from pydicom.tag import Tag

from MedBlend.structure import (
    _build_geometry,
    _build_geometry_from_contours,
    _get_structure_frame_uid,
    _load_reference_image_slices,
    _polygon_mask,
    _roi_display_color,
    crop_mask_to_bounds,
    iter_roi_masks,
)

from helpers import make_slice, write_slice


def build_reference_geometry(num_slices: int = 6, size: int = 16, spacing: float = 2.0):
    """Geometry for an axial series with non-unit, non-square voxel spacing."""

    slices = []
    for index in range(num_slices):
        ds = make_slice(index * 3.0, rows=size, cols=size, instance=index)
        ds.PixelSpacing = [spacing, spacing / 2.0]
        slices.append(ds)
    return _build_geometry(slices)


def patient_point(geometry, row: float, col: float, slice_index: float) -> np.ndarray:
    """Patient-space mm for a voxel index, using the geometry's own basis."""

    basis = np.asarray(geometry["basis"], dtype=float)
    origin = np.asarray(geometry["origin"], dtype=float)
    return origin + basis @ np.asarray([row, col, slice_index], dtype=float)


class TestPolygonMask:
    def test_axis_aligned_square(self):
        square = np.array([[2.0, 2.0], [2.0, 5.0], [5.0, 5.0], [5.0, 2.0]])
        mask = _polygon_mask((8, 8), square)
        rows, cols = np.nonzero(mask)
        assert rows.min() == 2 and cols.min() == 2
        assert mask.sum() > 0
        # Interior samples are unambiguous regardless of the boundary rule.
        assert mask[3, 3] and mask[4, 4]
        assert not mask[0, 0] and not mask[7, 7]

    def test_polygon_entirely_outside_grid_is_empty(self):
        far_away = np.array([[50.0, 50.0], [50.0, 60.0], [60.0, 60.0], [60.0, 50.0]])
        assert not _polygon_mask((8, 8), far_away).any()

    def test_polygon_is_clipped_to_grid(self):
        overhang = np.array([[-5.0, -5.0], [-5.0, 50.0], [50.0, 50.0], [50.0, -5.0]])
        mask = _polygon_mask((8, 8), overhang)
        assert mask.shape == (8, 8)
        assert mask.all()

    def test_degenerate_polygon_is_empty(self):
        assert not _polygon_mask((8, 8), np.array([[1.0, 1.0], [2.0, 2.0]])).any()

    def test_horizontal_only_polygon_is_empty(self):
        # Every edge lies along a scanline, so nothing can be crossed.
        flat = np.array([[3.0, 1.0], [3.0, 5.0], [3.0, 9.0]])
        assert not _polygon_mask((8, 12), flat).any()

    def test_concave_polygon_excludes_the_notch(self):
        # A "C" shape: parity filling must leave the notch empty.
        notched = np.array(
            [[1.0, 1.0], [1.0, 8.0], [3.0, 8.0], [3.0, 3.0], [6.0, 3.0], [6.0, 8.0], [8.0, 8.0], [8.0, 1.0]]
        )
        mask = _polygon_mask((10, 10), notched)
        assert mask[2, 5] and mask[7, 5] and mask[4, 2]
        assert not mask[4, 6] and not mask[5, 7]

    def test_matches_a_brute_force_even_odd_reference(self):
        """The fast scanline fill must agree with the naive per-edge test."""

        def reference(shape, polygon):
            rows, cols = shape
            poly_r, poly_c = polygon[:, 0], polygon[:, 1]
            out = np.zeros(shape, dtype=bool)
            for r in range(rows):
                for c in range(cols):
                    inside = False
                    for i in range(len(poly_r)):
                        yi, yj = poly_r[i], poly_r[(i + 1) % len(poly_r)]
                        xi, xj = poly_c[i], poly_c[(i + 1) % len(poly_c)]
                        if yi == yj:
                            continue
                        if ((yi > r) != (yj > r)) and c < (xj - xi) * (r - yi) / (yj - yi) + xi:
                            inside = not inside
                    out[r, c] = inside
            return out

        rng = np.random.default_rng(2024)
        for trial in range(60):
            polygon = rng.uniform(-4.0, 18.0, size=(int(rng.integers(3, 12)), 2))
            if trial % 3 == 0:
                # Vertices exactly on voxel centres are the boundary-rule worst case.
                polygon = np.round(polygon)
            assert np.array_equal(_polygon_mask((14, 14), polygon), reference((14, 14), polygon))


class TestCropMaskToBounds:
    def test_crop_preserves_patient_coordinates(self):
        geometry = build_reference_geometry()
        rows, cols = geometry["rows"], geometry["cols"]
        mask = np.zeros((geometry["num_slices"], rows, cols), dtype=bool)
        mask[2:4, 5:9, 6:11] = True

        cropped, cropped_origin = crop_mask_to_bounds(mask, geometry)
        assert cropped.shape == (2, 4, 5)

        # Every retained voxel must land on the same patient point as before.
        basis = np.asarray(geometry["basis"], dtype=float)
        for s, r, c in [(0, 0, 0), (1, 3, 4), (0, 2, 1)]:
            after = cropped_origin + basis @ np.asarray([r, c, s], dtype=float)
            before = patient_point(geometry, 5 + r, 6 + c, 2 + s)
            assert np.allclose(after, before)

    def test_empty_mask_keeps_original_origin(self):
        geometry = build_reference_geometry()
        mask = np.zeros((geometry["num_slices"], geometry["rows"], geometry["cols"]), dtype=bool)
        cropped, origin = crop_mask_to_bounds(mask, geometry)
        assert cropped.shape == mask.shape
        assert np.allclose(origin, geometry["origin"])

    def test_full_mask_is_unchanged(self):
        geometry = build_reference_geometry()
        mask = np.ones((geometry["num_slices"], geometry["rows"], geometry["cols"]), dtype=bool)
        cropped, origin = crop_mask_to_bounds(mask, geometry)
        assert cropped.shape == mask.shape
        assert np.allclose(origin, geometry["origin"])

    def test_crop_shrinks_a_small_roi_dramatically(self):
        geometry = build_reference_geometry(num_slices=40, size=256)
        mask = np.zeros((geometry["num_slices"], geometry["rows"], geometry["cols"]), dtype=bool)
        mask[10:14, 100:110, 100:110] = True
        cropped, _ = crop_mask_to_bounds(mask, geometry)
        assert cropped.size == 4 * 10 * 10
        assert cropped.size < mask.size / 1000


def make_structure_set(*, frame_uid: str = "1.9.9") -> Dataset:
    """RTSTRUCT with one square ROI drawn on two slices."""

    ds = Dataset()
    ds.Modality = "RTSTRUCT"
    ds.FrameOfReferenceUID = frame_uid

    roi = Dataset()
    roi.ROINumber = 1
    roi.ROIName = "Target"
    ds.StructureSetROISequence = [roi]

    contours = []
    for z in (3.0, 6.0):
        contour = Dataset()
        contour.ContourGeometricType = "CLOSED_PLANAR"
        # A square spanning several voxels, in patient mm.
        corners = [(4.0, 4.0), (4.0, 12.0), (12.0, 12.0), (12.0, 4.0)]
        contour.ContourData = [value for (x, y) in corners for value in (x, y, z)]
        contours.append(contour)

    roi_contour = Dataset()
    roi_contour.ReferencedROINumber = 1
    roi_contour.ROIDisplayColor = [255, 128, 0]
    roi_contour.ContourSequence = contours
    ds.ROIContourSequence = [roi_contour]
    return ds


class TestIterRoiMasks:
    def test_yields_named_bool_mask_with_color(self):
        geometry = build_reference_geometry()
        results = list(iter_roi_masks(make_structure_set(), geometry))
        assert len(results) == 1

        name, mask, color, skipped = results[0]
        assert name == "Target"
        # bool keeps peak memory at 1 byte/voxel instead of float64's 8.
        assert mask.dtype == np.bool_
        assert mask.any()
        assert skipped == 0
        assert color == pytest.approx((1.0, 128 / 255.0, 0.0, 1.0))

    def test_contours_are_rasterised_onto_the_expected_slices(self):
        geometry = build_reference_geometry()
        _name, mask, _color, _skipped = next(iter(iter_roi_masks(make_structure_set(), geometry)))
        occupied_slices = sorted(set(np.nonzero(mask)[0].tolist()))
        # Slices sit at z = 0, 3, 6, ...; contours were drawn at z = 3 and 6.
        assert occupied_slices == [1, 2]

    def test_out_of_range_contours_are_counted_not_silently_lost(self):
        structure = make_structure_set()
        stray = Dataset()
        stray.ContourGeometricType = "CLOSED_PLANAR"
        # z = 900 mm is far beyond the reconstructed slice range.
        stray.ContourData = [4.0, 4.0, 900.0, 4.0, 12.0, 900.0, 12.0, 12.0, 900.0]
        structure.ROIContourSequence[0].ContourSequence.append(stray)

        geometry = build_reference_geometry()
        _name, _mask, _color, skipped = next(iter(iter_roi_masks(structure, geometry)))
        assert skipped == 1

    def test_open_contours_and_points_are_ignored(self):
        structure = make_structure_set()
        for geometric_type in ("POINT", "OPEN_PLANAR"):
            extra = Dataset()
            extra.ContourGeometricType = geometric_type
            extra.ContourData = [4.0, 4.0, 3.0, 4.0, 12.0, 3.0, 12.0, 12.0, 3.0]
            structure.ROIContourSequence[0].ContourSequence.append(extra)

        geometry = build_reference_geometry()
        _name, with_extras, _color, _skipped = next(iter(iter_roi_masks(structure, geometry)))
        _name, baseline, _color, _skipped = next(iter(iter_roi_masks(make_structure_set(), geometry)))
        assert np.array_equal(with_extras, baseline)

    def test_roi_without_contours_yields_an_empty_mask(self):
        # Reported rather than dropped, so the user learns the ROI is missing.
        structure = make_structure_set()
        structure.ROIContourSequence[0].ContourSequence = []
        results = list(iter_roi_masks(structure, build_reference_geometry()))
        assert len(results) == 1
        name, mask, _color, skipped = results[0]
        assert (name, mask, skipped) == ("Target", None, 0)

    def test_roi_entirely_outside_the_grid_reports_its_skipped_contours(self):
        structure = make_structure_set()
        for contour in structure.ROIContourSequence[0].ContourSequence:
            data = list(contour.ContourData)
            data[2::3] = [900.0] * (len(data) // 3)
            contour.ContourData = data

        name, mask, _color, skipped = next(iter(iter_roi_masks(structure, build_reference_geometry())))
        assert (name, mask) == ("Target", None)
        assert skipped == 2

    def test_is_lazy(self):
        # A generator keeps only one ROI volume resident at a time.
        result = iter_roi_masks(make_structure_set(), build_reference_geometry())
        assert hasattr(result, "__next__")

    @pytest.mark.parametrize("empty_value", [None, ""])
    def test_empty_geometric_type_defaults_to_closed_planar(self, empty_value):
        # ContourGeometricType is Type 1 but exports do leave it empty. Treating
        # the resulting None as a type name dropped the whole ROI in silence.
        structure = make_structure_set()
        for contour in structure.ROIContourSequence[0].ContourSequence:
            contour.ContourGeometricType = empty_value

        _name, mask, _color, skipped = next(iter(iter_roi_masks(structure, build_reference_geometry())))
        _name, baseline, _color, _skipped = next(
            iter(iter_roi_masks(make_structure_set(), build_reference_geometry()))
        )
        assert mask is not None
        assert np.array_equal(mask, baseline)
        assert skipped == 0

    @pytest.mark.parametrize("bad_z", [float("nan"), float("inf")])
    def test_malformed_contour_is_skipped_not_fatal(self, bad_z):
        # Non-finite coordinates used to raise out of the rasteriser and
        # abandon every ROI still queued behind this one.
        structure = make_structure_set()
        broken = Dataset()
        broken.ContourGeometricType = "CLOSED_PLANAR"
        broken.ContourData = [4.0, 4.0, bad_z, 4.0, 12.0, bad_z, 12.0, 12.0, bad_z]
        structure.ROIContourSequence[0].ContourSequence.insert(0, broken)

        name, mask, _color, skipped = next(iter(iter_roi_masks(structure, build_reference_geometry())))
        assert name == "Target"
        assert skipped == 1
        # The two good contours behind it still rasterised.
        _n, baseline, _c, _s = next(iter(iter_roi_masks(make_structure_set(), build_reference_geometry())))
        assert np.array_equal(mask, baseline)

    def test_non_numeric_contour_data_is_skipped(self):
        # A malformed DS in a real file reaches Python as raw strings rather
        # than floats, so the failure lands in the numpy conversion.
        structure = make_structure_set()
        broken = Dataset()
        broken.ContourGeometricType = "CLOSED_PLANAR"
        broken[0x30060050] = RawDataElement(
            Tag(0x30060050), "DS", 35, b"1.0\\abc\\3.0\\1.0\\2.0\\3.0\\1.0\\2.0\\3.0", 0, True, True
        )
        structure.ROIContourSequence[0].ContourSequence.append(broken)

        _name, mask, _color, skipped = next(iter(iter_roi_masks(structure, build_reference_geometry())))
        assert mask is not None and mask.any()
        assert skipped == 1

    def test_padded_geometric_type_is_accepted(self):
        structure = make_structure_set()
        for contour in structure.ROIContourSequence[0].ContourSequence:
            contour.ContourGeometricType = " closed_planar "
        _name, mask, _color, _skipped = next(iter(iter_roi_masks(structure, build_reference_geometry())))
        assert mask is not None and mask.any()


class TestGeometryFallbacks:
    def test_contour_only_geometry_covers_all_points(self):
        geometry = _build_geometry_from_contours(make_structure_set())
        assert geometry["rows"] > 0 and geometry["cols"] > 0
        assert geometry["num_slices"] >= 2
        assert len(geometry["spacing"]) == 3
        # Masks generated from it must still land inside the grid.
        results = list(iter_roi_masks(make_structure_set(), geometry))
        assert results and results[0][1].any()

    def test_build_geometry_rejects_bad_orientation(self):
        bad = make_slice(0.0)
        bad.ImageOrientationPatient = [1, 0, 0, 1, 0, 0]  # parallel vectors
        with pytest.raises(ValueError, match="Invalid orientation"):
            _build_geometry([bad])

    def test_build_geometry_rejects_missing_pixel_spacing(self):
        bad = make_slice(0.0)
        bad.PixelSpacing = [0.0, 0.0]
        with pytest.raises(ValueError, match="invalid PixelSpacing"):
            _build_geometry([bad])

    def test_build_geometry_uses_slice_thickness_for_single_slice(self):
        geometry = _build_geometry([make_slice(0.0)])
        assert geometry["spacing"][0] == pytest.approx(2.0)

    def test_build_geometry_survives_empty_slice_thickness(self):
        only = make_slice(0.0)
        only.SliceThickness = None
        geometry = _build_geometry([only])
        assert geometry["spacing"][0] == pytest.approx(1.0)

    def test_build_geometry_rejects_non_uniform_slice_positions(self):
        slices = [make_slice(z, instance=i) for i, z in enumerate([0.0, 3.0, 6.0, 20.0])]
        with pytest.raises(ValueError, match="slice spacing is non-uniform"):
            _build_geometry(slices)

    def test_build_geometry_rejects_inconsistent_pixel_spacing(self):
        slices = [make_slice(0.0, instance=0), make_slice(2.0, instance=1)]
        slices[1].PixelSpacing = [1.0, 2.0]
        with pytest.raises(ValueError, match="inconsistent PixelSpacing"):
            _build_geometry(slices)

    def test_build_geometry_rejects_inconsistent_matrix_size(self):
        slices = [make_slice(0.0, instance=0), make_slice(2.0, rows=3, instance=1)]
        with pytest.raises(ValueError, match="Rows/Columns"):
            _build_geometry(slices)


class TestLoadReferenceImageSlices:
    def _write_series(self, folder, names, z_values=(0.0, 3.0, 6.0, 9.0)):
        for index, z in enumerate(z_values):
            for name in names:
                write_slice(folder, make_slice(z, rows=8, cols=8, instance=index), name.format(index))

    def test_duplicate_files_are_counted_once(self, tmp_path):
        # A duplicated export ("IMG1.dcm" and "IMG1 (1).dcm") must not deepen
        # the mask grid - every ROI allocates num_slices x rows x cols.
        self._write_series(tmp_path, ["img{}.dcm", "img{} (1).dcm"])
        slices = _load_reference_image_slices(tmp_path, make_structure_set())
        assert len(slices) == 4
        assert _build_geometry(slices)["num_slices"] == 4

    def test_distinct_slices_are_all_kept(self, tmp_path):
        self._write_series(tmp_path, ["img{}.dcm"])
        assert len(_load_reference_image_slices(tmp_path, make_structure_set())) == 4

    def test_other_series_are_ignored(self, tmp_path):
        self._write_series(tmp_path, ["img{}.dcm"])
        stray = make_slice(0.0, rows=8, cols=8, instance=99, series_uid="9.9.9")
        write_slice(tmp_path, stray, "other.dcm")

        structure = make_structure_set()
        series_ref = Dataset()
        series_ref.SeriesInstanceUID = "1.2.3"
        study_ref = Dataset()
        study_ref.RTReferencedSeriesSequence = [series_ref]
        frame_ref = Dataset()
        frame_ref.RTReferencedStudySequence = [study_ref]
        structure.ReferencedFrameOfReferenceSequence = [frame_ref]

        slices = _load_reference_image_slices(tmp_path, structure)
        assert {str(ds.SeriesInstanceUID) for ds in slices} == {"1.2.3"}

    def test_ambiguous_directory_without_references_is_rejected(self, tmp_path):
        self._write_series(tmp_path, ["primary{}.dcm"])
        for index, z in enumerate((0.0, 3.0, 6.0, 9.0)):
            write_slice(
                tmp_path,
                make_slice(z, rows=8, cols=8, instance=index, series_uid="9.9.9"),
                f"other{index}.dcm",
            )

        with pytest.raises(ValueError, match="multiple CT/MR series"):
            _load_reference_image_slices(tmp_path, make_structure_set())

    def test_contour_image_reference_resolves_one_series(self, tmp_path):
        self._write_series(tmp_path, ["primary{}.dcm"])
        for index, z in enumerate((0.0, 3.0, 6.0, 9.0)):
            write_slice(
                tmp_path,
                make_slice(z, rows=8, cols=8, instance=index, series_uid="9.9.9"),
                f"other{index}.dcm",
            )

        structure = make_structure_set()
        contour_image = Dataset()
        contour_image.ReferencedSOPInstanceUID = "9.9.9.1"
        structure.ROIContourSequence[0].ContourSequence[0].ContourImageSequence = [contour_image]

        slices = _load_reference_image_slices(tmp_path, structure)
        assert len(slices) == 4
        assert {str(ds.SeriesInstanceUID) for ds in slices} == {"9.9.9"}

    def test_multiple_explicit_series_references_are_rejected(self, tmp_path):
        self._write_series(tmp_path, ["primary{}.dcm"])

        series_refs = []
        for series_uid in ("1.2.3", "9.9.9"):
            series_ref = Dataset()
            series_ref.SeriesInstanceUID = series_uid
            series_refs.append(series_ref)
        study_ref = Dataset()
        study_ref.RTReferencedSeriesSequence = series_refs
        frame_ref = Dataset()
        frame_ref.RTReferencedStudySequence = [study_ref]
        structure = make_structure_set()
        structure.ReferencedFrameOfReferenceSequence = [frame_ref]

        with pytest.raises(ValueError, match="explicitly references multiple"):
            _load_reference_image_slices(tmp_path, structure)


class TestStructureMetadata:
    def test_frame_uid_read_from_top_level(self):
        assert _get_structure_frame_uid(make_structure_set(frame_uid="1.2.3")) == "1.2.3"

    def test_frame_uid_falls_back_to_referenced_sequence(self):
        ds = Dataset()
        ds.Modality = "RTSTRUCT"
        reference = Dataset()
        reference.FrameOfReferenceUID = "4.5.6"
        ds.ReferencedFrameOfReferenceSequence = [reference]
        assert _get_structure_frame_uid(ds) == "4.5.6"

    def test_missing_frame_uid_is_empty(self):
        ds = Dataset()
        ds.Modality = "RTSTRUCT"
        assert _get_structure_frame_uid(ds) == ""

    def test_display_color_is_normalised(self):
        roi = Dataset()
        roi.ROIDisplayColor = [0, 255, 51]
        assert _roi_display_color(roi) == pytest.approx((0.0, 1.0, 0.2, 1.0))

    def test_missing_or_malformed_display_color_is_none(self):
        assert _roi_display_color(Dataset()) is None
        partial = Dataset()
        partial.ROIDisplayColor = [255]
        assert _roi_display_color(partial) is None
