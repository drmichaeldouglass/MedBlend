"""Tests for per-ROI material tinting and how import failures are reported."""

from __future__ import annotations

import numpy as np
import pytest

import bpy
from MedBlend import node_groups, volume_utils


class FakeRegistry:
    """Stand-in for ``bpy.data.materials``: a name-keyed datablock table."""

    def __init__(self):
        self._by_name: dict[str, "FakeMaterial"] = {}

    def get(self, name, default=None):
        return self._by_name.get(name, default)

    def __contains__(self, name):
        return name in self._by_name

    def __len__(self):
        return len(self._by_name)

    def names(self):
        return sorted(self._by_name)

    def _register(self, material, previous=None):
        if previous is not None:
            self._by_name.pop(previous, None)
        self._by_name[material.name] = material


class FakeMaterial:
    def __init__(self, name, registry, copies=None):
        self._registry = registry
        self._name = name
        self.diffuse_color = (1.0, 1.0, 1.0, 1.0)
        self.node_tree = None
        self.copies = copies if copies is not None else []
        registry._register(self)

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        previous, self._name = self._name, value
        self._registry._register(self, previous)

    def copy(self):
        # Blender uniquifies a copy's name, then the caller renames it.
        clone = FakeMaterial(f"{self._name}.001", self._registry, self.copies)
        clone.diffuse_color = tuple(self.diffuse_color)
        self.copies.append(clone)
        return clone


class FakeObject:
    def __init__(self):
        self.data = type("Data", (), {"materials": []})()


@pytest.fixture
def materials(monkeypatch):
    registry = FakeRegistry()
    FakeMaterial("Structure Material", registry)
    monkeypatch.setattr(bpy.data, "materials", registry, raising=False)
    return registry


ORANGE = (1.0, 0.5, 0.0, 1.0)
BLUE = (0.0, 0.25, 1.0, 1.0)


class TestStructureMaterialTinting:
    def test_first_import_creates_a_tinted_copy(self, materials):
        obj = FakeObject()
        assert node_groups.apply_structure_material(obj, "Lung", ORANGE)

        assert "Structure Material - Lung" in materials
        assert obj.data.materials[0].diffuse_color == pytest.approx(ORANGE)

    def test_same_roi_and_colour_reuses_one_datablock(self, materials):
        first, second = FakeObject(), FakeObject()
        node_groups.apply_structure_material(first, "Lung", ORANGE)
        node_groups.apply_structure_material(second, "Lung", ORANGE)

        assert first.data.materials[0] is second.data.materials[0]
        assert len(materials) == 2  # base + one tint

    def test_same_roi_name_with_a_different_colour_gets_its_own_tint(self, materials):
        # Two structure sets can name an ROI identically and colour it
        # differently; reusing on name alone gave the second the first's colour.
        first, second = FakeObject(), FakeObject()
        node_groups.apply_structure_material(first, "Lung", ORANGE)
        node_groups.apply_structure_material(second, "Lung", BLUE)

        assert first.data.materials[0] is not second.data.materials[0]
        assert first.data.materials[0].diffuse_color == pytest.approx(ORANGE)
        assert second.data.materials[0].diffuse_color == pytest.approx(BLUE)

    def test_reimporting_does_not_accumulate_copies(self, materials):
        for _ in range(5):
            node_groups.apply_structure_material(FakeObject(), "Lung", ORANGE)
        assert len(materials) == 2

    def test_long_roi_names_stay_within_blenders_name_limit(self, materials):
        # A name Blender would truncate never matches the cache, so every
        # re-import would copy the material again.
        roi_name = "Right Parotid Gland Planning Risk Volume With A Long Suffix"
        for _ in range(4):
            node_groups.apply_structure_material(FakeObject(), roi_name, ORANGE)

        tints = [name for name in materials.names() if name != "Structure Material"]
        assert len(tints) == 1
        assert len(tints[0]) <= node_groups._MAX_DATABLOCK_NAME

    def test_no_colour_falls_back_to_the_shared_material(self, materials):
        obj = FakeObject()
        assert node_groups.apply_structure_material(obj, "Lung", None)
        assert obj.data.materials[0] is materials.get("Structure Material")
        assert len(materials) == 1


class TestWriteVdbErrorRouting:
    def _spy(self, monkeypatch):
        shown = []
        monkeypatch.setattr(volume_utils, "show_message_box", lambda *a, **k: shown.append(a))
        return shown

    def test_on_error_collects_instead_of_popping(self, monkeypatch):
        shown = self._spy(monkeypatch)
        errors: list[str] = []

        result = volume_utils.write_vdb_volume(
            np.zeros((2, 2, 2)), [0.0, 1.0, 1.0], "roi.vdb", on_error=errors.append
        )

        assert result is None
        assert len(errors) == 1 and "positive" in errors[0]
        assert shown == []

    def test_default_still_reports_to_the_user(self, monkeypatch):
        shown = self._spy(monkeypatch)
        assert volume_utils.write_vdb_volume(np.zeros((2, 2, 2)), [0.0, 1.0, 1.0], "roi.vdb") is None
        assert len(shown) == 1

    @pytest.mark.parametrize(
        "array,spacing,expected",
        [
            (np.zeros((2, 2, 2)), [1.0, 1.0], "3 spacing values"),
            (np.zeros((2, 2)), [1.0, 1.0, 1.0], "non-empty 3D"),
            (np.zeros((0, 2, 2)), [1.0, 1.0, 1.0], "non-empty 3D"),
        ],
    )
    def test_every_validation_failure_is_routed(self, monkeypatch, array, spacing, expected):
        shown = self._spy(monkeypatch)
        errors: list[str] = []

        assert volume_utils.write_vdb_volume(array, spacing, "roi.vdb", on_error=errors.append) is None
        assert len(errors) == 1 and expected in errors[0]
        assert shown == []

    def test_many_failing_rois_produce_one_report(self, monkeypatch):
        # A structure set that cannot be written fails identically for every
        # ROI; one dialog each used to bury the scene in popups.
        shown = self._spy(monkeypatch)
        errors: list[str] = []
        for index in range(30):
            volume_utils.write_vdb_volume(
                np.zeros((2, 2, 2)), [0.0, 1.0, 1.0], f"roi{index}.vdb", on_error=errors.append
            )
        assert shown == []
        assert len(errors) == 30
