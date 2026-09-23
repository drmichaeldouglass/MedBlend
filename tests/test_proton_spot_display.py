"""Tests for how imported proton spots are sized and coloured."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydicom.dataset import Dataset

import bpy
from MedBlend import node_groups, plan

from test_materials_and_reporting import FakeMaterial, FakeNode, FakeNodeTree, FakeRegistry


class FakeSetMaterialNode(FakeNode):
    bl_idname = "GeometryNodeSetMaterial"

    def __init__(self, name, material):
        super().__init__(("Material",))
        self.name = name
        self.inputs["Material"].default_value = material

    def copy(self):
        return FakeSetMaterialNode(self.name, self.inputs["Material"].default_value)


class FakeNodeList(list):
    def __getitem__(self, key):
        if isinstance(key, str):
            return next(node for node in self if node.name == key)
        return super().__getitem__(key)


class FakeNodeGroup:
    def __init__(self, name, registry, nodes):
        self._registry = registry
        self._name = name
        self.nodes = FakeNodeList(nodes)
        self.id_properties = {}
        self.interface = SimpleNamespace(
            items_tree=[SimpleNamespace(in_out="INPUT", name="Spot Size", identifier="Socket_3")]
        )
        registry._register(self)

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        previous, self._name = self._name, value
        self._registry._register(self, previous)

    def __setitem__(self, key, value):
        self.id_properties[key] = value

    def get(self, key, default=None):
        return self.id_properties.get(key, default)

    def copy(self):
        return FakeNodeGroup(
            f"{self._name}.001", self._registry, [node.copy() for node in self.nodes]
        )


class FakeModifier(dict):
    node_group = None


class FakeModifiers:
    def __init__(self):
        self._modifiers = {}

    def get(self, name):
        return self._modifiers.get(name)

    def new(self, name, _type):
        self._modifiers[name] = FakeModifier()
        return self._modifiers[name]


class FakeSpotObject:
    def __init__(self):
        self.modifiers = FakeModifiers()


def spot_window_of(material):
    group = material.node_tree.nodes[-1]
    return (
        group.inputs["Min Spot Weight"].default_value,
        group.inputs["Max Spot Weight"].default_value,
    )


@pytest.fixture
def spot_assets(monkeypatch):
    """The shipped Proton_Spots node group and the Spot Material it sets."""

    materials, groups = FakeRegistry(), FakeRegistry()
    shader_group = FakeNode(("Min Spot Weight", "Max Spot Weight", "Spot Intensity"))
    shader_group.inputs["Max Spot Weight"].default_value = 12.97
    spot_material = FakeMaterial(
        "Spot Material", materials, node_tree=FakeNodeTree([FakeNode(()), shader_group])
    )
    beam_material = FakeMaterial("Proton Beam", materials, node_tree=FakeNodeTree([FakeNode(())]))
    FakeNodeGroup(
        "Proton_Spots",
        groups,
        [
            FakeSetMaterialNode("Set Material", spot_material),
            FakeSetMaterialNode("Set Material.001", beam_material),
        ],
    )
    monkeypatch.setattr(bpy.data, "materials", materials, raising=False)
    monkeypatch.setattr(bpy.data, "node_groups", groups, raising=False)
    return SimpleNamespace(materials=materials, groups=groups)


def spot_material_of(modifier):
    return modifier.node_group.nodes["Set Material"].inputs["Material"].default_value


class TestSpotDisplay:
    def test_the_spot_colours_are_windowed_onto_the_plan_weights(self, spot_assets):
        modifier = node_groups.apply_proton_spots_geo_nodes(
            obj=FakeSpotObject(), weight_range=(0.0, 0.4)
        )

        assert modifier.node_group is not spot_assets.groups.get("Proton_Spots")
        assert spot_window_of(spot_material_of(modifier)) == (0.0, 0.4)
        # The shared assets stay as shipped.
        assert spot_window_of(spot_assets.materials.get("Spot Material")) == (0.0, 12.97)
        shared = spot_assets.groups.get("Proton_Spots")
        assert spot_material_of(SimpleNamespace(node_group=shared)).name == "Spot Material"

    def test_the_beam_material_is_left_alone(self, spot_assets):
        modifier = node_groups.apply_proton_spots_geo_nodes(
            obj=FakeSpotObject(), weight_range=(0.0, 0.4)
        )
        beam = modifier.node_group.nodes["Set Material.001"].inputs["Material"].default_value
        assert beam is spot_assets.materials.get("Proton Beam")

    @pytest.mark.parametrize("max_weight", [0.4, 12.97, 250.0])
    def test_the_heaviest_spot_always_gets_the_same_radius(self, spot_assets, max_weight):
        modifier = node_groups.apply_proton_spots_geo_nodes(
            obj=FakeSpotObject(), weight_range=(0.0, max_weight)
        )
        assert modifier["Socket_3"] * max_weight == pytest.approx(node_groups.MAX_SPOT_RADIUS)

    def test_the_same_weights_reuse_one_copy(self, spot_assets):
        first = node_groups.apply_proton_spots_geo_nodes(
            obj=FakeSpotObject(), weight_range=(0.0, 0.4)
        )
        second = node_groups.apply_proton_spots_geo_nodes(
            obj=FakeSpotObject(), weight_range=(0.0, 0.4)
        )

        assert first.node_group is second.node_group
        assert len(spot_assets.groups) == 2
        assert len(spot_assets.materials) == 3

    @pytest.mark.parametrize("weight_range", [None, (0.0, 0.0)], ids=["missing", "all-zero"])
    def test_no_usable_weights_keep_the_shipped_node_group(self, spot_assets, weight_range):
        modifier = node_groups.apply_proton_spots_geo_nodes(
            obj=FakeSpotObject(), weight_range=weight_range
        )
        assert modifier.node_group is spot_assets.groups.get("Proton_Spots")
        assert "Socket_3" not in modifier


class FakeAttribute:
    def __init__(self):
        self.values = []
        self.data = SimpleNamespace(foreach_set=lambda _key, values: self.values.extend(values))


class FakeAttributes(dict):
    def new(self, name, type, domain):
        self[name] = FakeAttribute()
        return self[name]


class FakeVertices(list):
    def add(self, count):
        self.extend([None] * count)

    def foreach_set(self, _key, _values):
        pass


class FakeMesh:
    def __init__(self, name):
        self.name = name
        self.vertices = FakeVertices()
        self.attributes = FakeAttributes()

    def validate(self):
        pass

    def update(self):
        pass


class FakePlanObject(dict):
    matrix_world = None


def make_beam(number, weights):
    beam = Dataset()
    beam.BeamNumber = number
    beam.RadiationType = "PROTON"
    first = Dataset()
    first.GantryAngle = 0
    first.PatientSupportAngle = 0
    first.IsocenterPosition = [0, 0, 0]
    first.NominalBeamEnergy = 100
    first.NumberOfScanSpotPositions = len(weights)
    first.ScanSpotPositionMap = [float(value) for value in range(2 * len(weights))]
    first.ScanSpotMetersetWeights = list(weights)
    last = Dataset()
    last.NominalBeamEnergy = 100
    beam.IonControlPointSequence = [first, last]
    return beam


class TestPlanSpotWindow:
    def test_every_beam_shares_the_plan_wide_weight_range(self, monkeypatch, tmp_path):
        ds = Dataset()
        ds.Modality = "RTPLAN"
        ds.SOPClassUID = plan.RT_ION_PLAN_STORAGE_UID
        ds.IonBeamSequence = [make_beam(1, [0.5, 2.0]), make_beam(2, [8.0, 1.0])]
        monkeypatch.setattr(plan.pydicom, "dcmread", lambda _path: ds)
        monkeypatch.setattr(
            plan.bpy, "data", SimpleNamespace(meshes=SimpleNamespace(new=FakeMesh)), raising=False
        )
        monkeypatch.setattr(plan, "create_object", lambda _mesh, _name: FakePlanObject())
        monkeypatch.setattr(plan, "show_message_box", lambda *a, **k: None)
        calls = []
        monkeypatch.setattr(
            plan, "apply_proton_spots_geo_nodes", lambda **kwargs: calls.append(kwargs)
        )

        assert plan.load_proton_plan(tmp_path / "plan.dcm") is True
        # Windowing each beam on its own weights would make a lightly
        # weighted beam look as heavy as the main one.
        assert [call["weight_range"] for call in calls] == [(0.0, 8.0), (0.0, 8.0)]
