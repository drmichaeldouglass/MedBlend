"""Proton patient setups, asset loading, and import robustness."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import numpy as np
import pytest
from pydicom.dataset import Dataset

import bpy
from MedBlend import blender_utils, node_groups, volume_materials
from MedBlend import plan as plan_module
from MedBlend.photon_fluence import _rotation
from MedBlend.plan import (
    _BeamGeometry,
    _beam_world_matrix_from_geometry,
    _patient_position,
    is_supported_setup,
    setup_rotation,
)
from MedBlend.presets import VOLUME_PRESETS
from MedBlend.structure import _build_geometry_from_contours


# ---------------------------------------------------------------------------
# Proton beams follow the patient setup
# ---------------------------------------------------------------------------


def source_direction(position: str, gantry: float, couch: float = 0.0) -> np.ndarray:
    """Unit vector from isocentre towards the source, in DICOM patient axes."""

    geometry = _BeamGeometry(gantry, couch, (0.0, 0.0, 0.0))
    matrix = _beam_world_matrix_from_geometry(geometry, setup_rotation(position))
    return np.asarray(matrix.rows)[:3, 2]


LEFT, POSTERIOR, SUPERIOR = np.eye(3)


@pytest.mark.parametrize(
    ("position", "gantry", "expected"),
    [
        # Gantry 0 is overhead: whichever side of the patient faces the ceiling.
        ("HFS", 0, -POSTERIOR),
        ("FFS", 0, -POSTERIOR),
        ("HFP", 0, POSTERIOR),
        ("FFP", 0, POSTERIOR),
        ("HFDL", 0, -LEFT),
        ("HFDR", 0, LEFT),
        ("FFDL", 0, -LEFT),
        ("FFDR", 0, LEFT),
        # Gantry 90 is on the room's +X side, the supine head-first left.
        ("HFS", 90, LEFT),
        ("FFS", 90, -LEFT),
        ("HFP", 90, -LEFT),
        ("FFP", 90, LEFT),
        ("HFDL", 90, -POSTERIOR),
        ("HFDR", 90, POSTERIOR),
    ],
)
def test_source_side_for_each_patient_position(position, gantry, expected):
    assert source_direction(position, gantry) == pytest.approx(expected, abs=1e-12)


@pytest.mark.parametrize(("position", "sign"), [("HFS", 1), ("HFP", 1), ("FFS", -1), ("FFP", -1)])
def test_spot_y_runs_towards_the_gantry_end_of_the_couch(position, sign):
    geometry = _BeamGeometry(0.0, 0.0, (0.0, 0.0, 0.0))
    matrix = _beam_world_matrix_from_geometry(geometry, setup_rotation(position))
    spot_y = np.asarray(matrix.rows)[:3, 1]
    assert spot_y == pytest.approx(sign * SUPERIOR, abs=1e-12)


def test_setup_rotation_is_applied_about_the_isocentre():
    geometry = _BeamGeometry(30.0, 15.0, (10.0, -20.0, 300.0))
    matrix = _beam_world_matrix_from_geometry(geometry, setup_rotation("FFP"))
    assert matrix.translation == pytest.approx((0.01, -0.02, 0.3))


def test_proton_and_photon_importers_agree_on_every_setup():
    for position in ("HFS", "HFP", "HFDL", "HFDR", "FFS", "FFP", "FFDL", "FFDR"):
        geometry = _BeamGeometry(37.0, 12.0, (0.0, 0.0, 0.0))
        proton = np.asarray(
            _beam_world_matrix_from_geometry(geometry, setup_rotation(position)).rows
        )[:3, :3]
        # Photon angle order is (gantry, collimator, couch).
        photon = _rotation(setup_rotation(position), (37.0, 0.0, 12.0))
        assert proton == pytest.approx(photon, abs=1e-12), position


def test_hfs_matrix_is_unchanged_by_the_setup_rotation():
    geometry = _BeamGeometry(120.0, 20.0, (1.0, 2.0, 3.0))
    plain = np.asarray(_beam_world_matrix_from_geometry(geometry).rows)
    hfs = np.asarray(_beam_world_matrix_from_geometry(geometry, setup_rotation("HFS")).rows)
    assert plain == pytest.approx(hfs)


@pytest.mark.parametrize("position", ["", "SITTING", "HF", "XXS", "HFX"])
def test_non_axial_positions_are_not_supported(position):
    assert not is_supported_setup(position)


def make_setup(number, position):
    setup = Dataset()
    setup.PatientSetupNumber = number
    setup.PatientPosition = position
    return setup


def test_patient_position_follows_the_beams_setup_reference():
    ds = Dataset()
    ds.PatientSetupSequence = [make_setup(1, "HFS"), make_setup(2, "ffp ")]
    beam = Dataset()
    beam.ReferencedPatientSetupNumber = 2
    assert _patient_position(ds, beam) == "FFP"
    assert _patient_position(ds) == "HFS"


def test_patient_position_falls_back_to_the_first_setup():
    ds = Dataset()
    ds.PatientSetupSequence = [make_setup(1, "HFP")]
    beam = Dataset()
    beam.ReferencedPatientSetupNumber = 7
    assert _patient_position(ds, beam) == "HFP"
    assert _patient_position(ds, Dataset()) == "HFP"


class FakeSpotObject(dict):
    matrix_world = None


def import_single_beam(monkeypatch, tmp_path, position):
    control_points = []
    for index in range(2):
        cp = Dataset()
        cp.NominalBeamEnergy = 150.0
        cp.ScanSpotPositionMap = [0.0, 0.0, 10.0, 0.0]
        cp.ScanSpotMetersetWeights = [1.0, 2.0] if index == 0 else [0.0, 0.0]
        if index == 0:
            cp.GantryAngle = 0.0
            cp.PatientSupportAngle = 0.0
            cp.IsocenterPosition = [0.0, 0.0, 0.0]
        control_points.append(cp)
    beam = Dataset()
    beam.RadiationType = "PROTON"
    beam.BeamNumber = 1
    beam.ReferencedPatientSetupNumber = 1
    beam.IonControlPointSequence = control_points
    ds = Dataset()
    ds.Modality = "RTPLAN"
    ds.SOPClassUID = plan_module.RT_ION_PLAN_STORAGE_UID
    ds.IonBeamSequence = [beam]
    ds.PatientSetupSequence = [make_setup(1, position)]

    created = []
    messages = []

    def create(_mesh, _name):
        created.append(FakeSpotObject())
        return created[-1]

    vertices = type(
        "Vertices", (list,), {"add": lambda self, n: None, "foreach_set": lambda self, *a: None}
    )([0, 1])
    mesh = SimpleNamespace(
        name="spots",
        vertices=vertices,
        attributes={
            key: SimpleNamespace(data=SimpleNamespace(foreach_set=lambda *_a: None))
            for key in ("spot_x", "spot_y", "spot_E", "spot_weight")
        },
        validate=lambda: None,
        update=lambda: None,
    )

    monkeypatch.setattr(plan_module.pydicom, "dcmread", lambda *_a, **_k: ds)
    monkeypatch.setattr(plan_module, "find_ct_anchor", lambda _uid: None)
    monkeypatch.setattr(plan_module, "add_data_fields", lambda *_a: None)
    monkeypatch.setattr(plan_module, "create_object", create)
    monkeypatch.setattr(plan_module, "apply_proton_spots_geo_nodes", lambda **_k: None)
    monkeypatch.setattr(plan_module, "show_message_box", lambda *a: messages.append(a))
    monkeypatch.setattr(
        plan_module.bpy.data, "meshes", SimpleNamespace(new=lambda name: mesh), raising=False
    )

    assert plan_module.load_proton_plan(tmp_path / "plan.dcm") is True
    return created, messages


def test_prone_plan_is_imported_with_the_beam_entering_posteriorly(monkeypatch, tmp_path):
    created, messages = import_single_beam(monkeypatch, tmp_path, "HFP")
    towards_source = np.asarray(created[0].matrix_world.rows)[:3, 2]
    assert towards_source == pytest.approx(POSTERIOR, abs=1e-12)
    # A supported setup is handled, not warned about.
    assert not messages


def test_unsupported_position_keeps_hfs_and_says_so(monkeypatch, tmp_path):
    created, messages = import_single_beam(monkeypatch, tmp_path, "SITTING")
    towards_source = np.asarray(created[0].matrix_world.rows)[:3, 2]
    assert towards_source == pytest.approx(-POSTERIOR, abs=1e-12)
    assert "unsupported patient position SITTING" in messages[0][0]


# ---------------------------------------------------------------------------
# Asset library loading
# ---------------------------------------------------------------------------


class FakeLibraries:
    def __init__(self, available, registry, fail=False):
        self.available = available
        self.registry = registry
        self.fail = fail
        self.calls = []

    @contextmanager
    def load(self, filepath, link=False):
        self.calls.append((filepath, link))
        if self.fail:
            raise OSError("cannot open library")
        data_from = SimpleNamespace(materials=list(self.available), node_groups=[])
        data_to = SimpleNamespace(materials=[], node_groups=[])
        yield data_from, data_to
        for name in data_to.materials:
            self.registry[name] = SimpleNamespace(name=name)


@pytest.fixture
def append_calls(monkeypatch):
    calls = []
    ops = SimpleNamespace(wm=SimpleNamespace(append=lambda **kw: calls.append(kw)))
    monkeypatch.setattr(node_groups.bpy, "ops", ops, raising=False)
    return calls


def test_assets_load_without_the_context_dependent_operator(monkeypatch, tmp_path, append_calls):
    registry = {}
    libraries = FakeLibraries(["Dose Material"], registry)
    monkeypatch.setattr(bpy.data, "libraries", libraries, raising=False)
    monkeypatch.setattr(bpy.data, "materials", registry, raising=False)

    node_groups.append_item_from_blend(tmp_path / "assets.blend", "Material", "Dose Material")

    assert "Dose Material" in registry
    assert libraries.calls == [(str(tmp_path / "assets.blend"), False)]
    assert not append_calls


@pytest.mark.parametrize("fail", [True, False])
def test_operator_is_the_fallback_when_the_library_load_yields_nothing(
    monkeypatch, tmp_path, append_calls, fail
):
    registry = {}
    libraries = FakeLibraries([], registry, fail=fail)
    monkeypatch.setattr(bpy.data, "libraries", libraries, raising=False)
    monkeypatch.setattr(bpy.data, "materials", registry, raising=False)

    node_groups.append_item_from_blend(tmp_path / "assets.blend", "Material", "Dose Material")

    assert len(append_calls) == 1
    assert append_calls[0]["filename"] == "Dose Material"


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------


def test_create_object_survives_a_view_layer_that_refuses_the_object(monkeypatch):
    class Objects:
        @property
        def active(self):
            return None

        @active.setter
        def active(self, _value):
            raise RuntimeError("object is not in the view layer")

    linked = []
    new_object = SimpleNamespace(select_set=lambda _state: None)
    context = SimpleNamespace(
        collection=SimpleNamespace(objects=SimpleNamespace(link=linked.append)),
        view_layer=SimpleNamespace(objects=Objects()),
    )
    monkeypatch.setattr(blender_utils.bpy, "context", context, raising=False)
    monkeypatch.setattr(
        blender_utils.bpy.data,
        "objects",
        SimpleNamespace(new=lambda _name, _mesh: new_object),
        raising=False,
    )

    assert blender_utils.create_object(object(), "spots") is new_object
    assert linked == [new_object]


def test_failed_preset_build_does_not_leave_a_material_behind(monkeypatch):
    class Registry(dict):
        def new(self, name):
            self[name] = SimpleNamespace(name=name)
            return self[name]

        def remove(self, material):
            del self[material.name]

    registry = Registry()
    monkeypatch.setattr(bpy.data, "materials", registry, raising=False)

    def explode(*_args, **_kwargs):
        raise RuntimeError("node type is unavailable")

    monkeypatch.setattr(volume_materials, "build_preset_node_tree", explode)

    with pytest.raises(RuntimeError):
        volume_materials.get_preset_material(VOLUME_PRESETS[0], (0.0, 1.0))
    assert not registry


def test_contour_only_grid_has_one_slice_per_plane():
    # 120 planes 0.3 mm apart: accumulated float error puts the extent a hair
    # past a whole number of steps, which must not add an empty slice.
    angles = np.linspace(0, 2 * np.pi, 24, endpoint=False)
    contours = []
    for index in range(120):
        points = np.stack(
            [10 * np.cos(angles), 10 * np.sin(angles), np.full(24, -123.4 + index * 0.3)],
            axis=1,
        )
        contour = Dataset()
        contour.ContourGeometricType = "CLOSED_PLANAR"
        contour.ContourData = [float(value) for value in points.reshape(-1)]
        contours.append(contour)
    roi = Dataset()
    roi.ContourSequence = contours
    structure = Dataset()
    structure.ROIContourSequence = [roi]

    assert _build_geometry_from_contours(structure)["num_slices"] == 120
