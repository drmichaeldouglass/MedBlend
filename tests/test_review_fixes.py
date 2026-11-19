"""Regressions for the volume background, ROI colour and VDB directory fixes."""

from __future__ import annotations

from pathlib import Path

import bpy
import numpy as np
import pytest
from helpers import make_slice, write_slice
from pydicom import Dataset

from MedBlend import ct as ct_module
from MedBlend import structure, volume_utils


class FakeGrid:
    def __init__(self, background=0.0):
        self.background = background
        self.voxels = None

    def copyFromArray(self, array):
        self.voxels = array

    def prune(self, _tolerance):
        pass


class FakeOpenVDB:
    """Just enough of the OpenVDB module for write_vdb_volume to run."""

    class GridClass:
        FOG_VOLUME = "FOG_VOLUME"

    FloatGrid = FakeGrid

    def __init__(self):
        self.written = []

    @staticmethod
    def createLinearTransform(matrix):
        return matrix

    def write(self, path, grid):
        Path(path).write_bytes(b"")
        self.written.append(grid)


class FakeVolumeObject(dict):
    def __init__(self):
        super().__init__()
        self.data = {}


@pytest.fixture
def vdb(tmp_path, monkeypatch):
    module = FakeOpenVDB()
    monkeypatch.setattr(volume_utils, "_import_openvdb_module", lambda: module)
    monkeypatch.setattr(volume_utils, "resolve_temp_path", lambda name: tmp_path / name)
    monkeypatch.setattr(
        volume_utils, "_import_volume_data_api", lambda _path: FakeVolumeObject()
    )
    return module


class TestVolumeBackground:
    """Outside a CT is air, not the 0 HU water OpenVDB assumes by default."""

    def test_the_default_background_is_zero(self, vdb):
        assert volume_utils.write_vdb_volume(np.ones((2, 2, 2)), [1, 1, 1], "dose.vdb")
        assert vdb.written[0].background == 0.0

    def test_a_requested_background_reaches_the_grid(self, vdb):
        array = np.full((2, 2, 2), -1000.0)
        assert volume_utils.write_vdb_volume(array, [1, 1, 1], "CT.vdb", background=-1000.0)
        assert vdb.written[0].background == -1000.0

    def test_a_build_without_the_constructor_argument_sets_the_property(self, vdb):
        class PropertyOnlyGrid(FakeGrid):
            def __init__(self):
                super().__init__()

        vdb.FloatGrid = PropertyOnlyGrid
        assert volume_utils.write_vdb_volume(
            np.ones((2, 2, 2)), [1, 1, 1], "CT.vdb", background=-1024.0
        )
        assert vdb.written[0].background == -1024.0

    def test_a_non_finite_background_falls_back_to_zero(self, vdb):
        assert volume_utils.write_vdb_volume(
            np.ones((2, 2, 2)), [1, 1, 1], "CT.vdb", background=float("nan")
        )
        assert vdb.written[0].background == 0.0

    def test_a_ct_import_uses_its_lowest_intensity(self, tmp_path, monkeypatch):
        for index in range(3):
            write_slice(
                tmp_path,
                make_slice(2.0 * index, instance=index + 1, value=100 * index),
                f"slice{index}.dcm",
            )
        calls = []

        def fake_write(_array, _spacing, _name, **kwargs):
            calls.append(kwargs)
            return None

        monkeypatch.setattr(ct_module, "write_vdb_volume", fake_write)
        ct_module.load_ct_series(tmp_path / "slice0.dcm")

        # make_slice stores 0/100/200 with RescaleIntercept -1024.
        assert calls == [{"background": -1024.0}]


class TestRoiColourSpace:
    """ROIDisplayColor is sRGB; Blender colours are scene-linear."""

    def test_extremes_are_unchanged(self):
        assert structure._scene_linear_color((1.0, 0.0, 1.0, 1.0)) == pytest.approx(
            (1.0, 0.0, 1.0, 1.0)
        )

    def test_mid_tones_are_linearised(self):
        red, green, blue, alpha = structure._scene_linear_color((1.0, 128 / 255.0, 0.0, 1.0))
        assert (red, blue, alpha) == (1.0, 0.0, 1.0)
        assert green == pytest.approx(0.2158605)

    def test_out_of_range_components_are_clamped(self):
        assert structure._scene_linear_color((2.0, -1.0, 0.0, 1.0)) == pytest.approx(
            (1.0, 0.0, 0.0, 1.0)
        )

    def test_an_imported_structure_is_tinted_in_scene_linear(self, tmp_path, monkeypatch):
        contour = Dataset()
        contour.ContourGeometricType = "CLOSED_PLANAR"
        contour.ContourData = [0, 0, 0, 8, 0, 0, 8, 8, 0, 0, 8, 0]
        roi_contour = Dataset()
        roi_contour.ReferencedROINumber = 1
        roi_contour.ROIDisplayColor = [255, 128, 0]
        roi_contour.ContourSequence = [contour]
        roi = Dataset()
        roi.ROINumber = 1
        roi.ROIName = "Target"
        dataset = Dataset()
        dataset.Modality = "RTSTRUCT"
        dataset.StructureSetROISequence = [roi]
        dataset.ROIContourSequence = [roi_contour]

        obj = FakeVolumeObject()
        tints = []
        monkeypatch.setattr(structure.pydicom, "dcmread", lambda *a, **k: dataset)
        monkeypatch.setattr(structure, "find_ct_anchor", lambda _uid: None)
        monkeypatch.setattr(structure, "set_object_patient_transform", lambda *a: None)
        monkeypatch.setattr(
            structure, "write_vdb_volume", lambda *a, **k: (tmp_path / "roi.vdb", obj)
        )
        monkeypatch.setattr(
            structure,
            "apply_structure_material",
            lambda _obj, _name, color: tints.append(color),
        )

        assert structure.load_structures(tmp_path / "rs.dcm") is True
        expected = (1.0, 0.2158605, 0.0, 1.0)
        assert obj.color == pytest.approx(expected)
        assert tints[0] == pytest.approx(expected)


class TestRelativeVdbDirectory:
    """A "//" directory means nothing until the scene has a file path."""

    @pytest.fixture
    def prefs(self, monkeypatch):
        class Prefs:
            vdb_temp_dir = "//volumes"

        class Addon:
            preferences = Prefs()

        class Addons:
            @staticmethod
            def get(_name):
                return Addon()

        class Preferences:
            addons = Addons()

        class Context:
            preferences = Preferences()

        monkeypatch.setattr(bpy, "context", Context(), raising=False)
        return Prefs

    def test_it_is_ignored_in_an_unsaved_scene(self, prefs, monkeypatch):
        monkeypatch.setattr(bpy.data, "filepath", "", raising=False)
        assert volume_utils._get_vdb_temp_dir() is None

    def test_it_is_used_once_the_scene_is_saved(self, prefs, monkeypatch, tmp_path):
        monkeypatch.setattr(bpy.data, "filepath", str(tmp_path / "scan.blend"), raising=False)
        monkeypatch.setattr(
            bpy.path,
            "abspath",
            staticmethod(lambda value: str(tmp_path / value[2:])),
            raising=False,
        )
        assert volume_utils._get_vdb_temp_dir() == tmp_path / "volumes"

    def test_an_absolute_directory_is_used_either_way(self, prefs, monkeypatch, tmp_path):
        prefs.vdb_temp_dir = str(tmp_path)
        monkeypatch.setattr(bpy.data, "filepath", "", raising=False)
        assert volume_utils._get_vdb_temp_dir() == tmp_path
