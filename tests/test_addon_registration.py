"""Tests for add-on registration, menu integration and operator reporting."""

from __future__ import annotations

import bpy
import pytest

import MedBlend
from MedBlend import presets


class FakePrefs:
    def __init__(self, vdb_temp_dir=""):
        self.vdb_temp_dir = vdb_temp_dir


def make_context(prefs):
    addon = None if prefs is None else type("_Addon", (), {"preferences": prefs})()
    addons = type("_Addons", (), {"get": staticmethod(lambda _name: addon)})()
    return type("_Ctx", (), {"preferences": type("_P", (), {"addons": addons})()})()


class TestRegistration:
    def test_register_unregister_round_trip(self):
        MedBlend.register()
        try:
            assert MedBlend._draw_file_import_menu in bpy.types.TOPBAR_MT_file_import._draw_funcs
        finally:
            MedBlend.unregister()
        assert MedBlend._draw_file_import_menu not in bpy.types.TOPBAR_MT_file_import._draw_funcs

    def test_registering_twice_leaves_one_menu_entry(self):
        # A stale callback would draw MedBlend's importers twice in File > Import.
        for _ in range(2):
            MedBlend.register()
            MedBlend.unregister()
        assert bpy.types.TOPBAR_MT_file_import._draw_funcs == []

    def test_unregister_without_register_does_not_raise(self):
        # Blender still calls unregister() when register() failed part-way;
        # raising here would abandon the rest of the teardown.
        MedBlend.unregister()
        assert bpy.types.TOPBAR_MT_file_import._draw_funcs == []

    def test_file_import_menu_lists_every_importer(self):
        operator_ids = {operator_id for operator_id, _label in MedBlend._FILE_IMPORT_ENTRIES}
        registered = {
            cls.bl_idname
            for cls in MedBlend.classes
            if str(getattr(cls, "bl_idname", "")).startswith("medblend.load_")
        }
        assert operator_ids == registered

    def test_menu_entries_are_labelled(self):
        for operator_id, label in MedBlend._FILE_IMPORT_ENTRIES:
            assert operator_id.startswith("medblend.")
            assert label and label[0].isupper()

    def test_every_declared_property_survives_annotation_evaluation(self):
        # Blender drops any annotation that is a plain string, which is what
        # `from __future__ import annotations` would turn every property into.
        for cls in MedBlend.classes:
            stringified = [
                name
                for name, value in getattr(cls, "__annotations__", {}).items()
                if isinstance(value, str)
            ]
            assert stringified == [], f"{cls.__name__} has deferred annotations"


class TestPresetEnums:
    @pytest.mark.parametrize(
        "items", [presets.PRESET_ENUM_ITEMS, presets.IMPORT_PRESET_ENUM_ITEMS]
    )
    def test_items_are_well_formed(self, items):
        entries = [item for item in items if item is not None]
        assert entries, "enum must offer at least one item"
        assert all(len(item) == 3 for item in entries)
        assert all(item[0] and item[1] and item[2] for item in entries)

    @pytest.mark.parametrize(
        "items", [presets.PRESET_ENUM_ITEMS, presets.IMPORT_PRESET_ENUM_ITEMS]
    )
    def test_identifiers_are_unique(self, items):
        identifiers = [item[0] for item in items if item is not None]
        assert len(identifiers) == len(set(identifiers))

    @pytest.mark.parametrize(
        "items,default",
        [
            (presets.PRESET_ENUM_ITEMS, presets.VOLUME_PRESETS[0].name),
            (presets.IMPORT_PRESET_ENUM_ITEMS, presets.NO_PRESET),
        ],
    )
    def test_default_is_a_real_item(self, items, default):
        assert default in {item[0] for item in items if item is not None}

    def test_a_separator_never_leads_or_trails(self):
        # Blender draws a leading or trailing None as an empty menu row.
        for items in (presets.PRESET_ENUM_ITEMS, presets.IMPORT_PRESET_ENUM_ITEMS):
            assert items[0] is not None
            assert items[-1] is not None


class TestVdbTempDirOperators:
    def test_empty_selection_is_rejected(self):
        prefs = FakePrefs(vdb_temp_dir="/existing/path")
        operator = MedBlend.MEDBLEND_OT_Select_Vdb_Temp_Dir()
        operator.directory = ""
        operator.filepath = ""
        reports = []
        operator.report = lambda level, message: reports.append((level, message))

        # Path("") is Path("."), which used to be accepted and silently pointed
        # the VDB directory at Blender's working directory.
        assert operator.execute(make_context(prefs)) == {"CANCELLED"}
        assert prefs.vdb_temp_dir == "/existing/path"
        assert reports and "ERROR" in reports[0][0]

    def test_selected_directory_is_stored(self, tmp_path):
        prefs = FakePrefs()
        operator = MedBlend.MEDBLEND_OT_Select_Vdb_Temp_Dir()
        operator.directory = str(tmp_path)
        operator.filepath = ""
        operator.report = lambda *_: None

        assert operator.execute(make_context(prefs)) == {"FINISHED"}
        assert prefs.vdb_temp_dir == str(tmp_path)

    def test_a_selected_file_stores_its_parent(self, tmp_path):
        target = tmp_path / "picked.vdb"
        target.write_text("x")
        prefs = FakePrefs()
        operator = MedBlend.MEDBLEND_OT_Select_Vdb_Temp_Dir()
        operator.directory = ""
        operator.filepath = str(target)
        operator.report = lambda *_: None

        assert operator.execute(make_context(prefs)) == {"FINISHED"}
        assert prefs.vdb_temp_dir == str(tmp_path)

    def test_missing_preferences_reports_rather_than_failing_silently(self):
        operator = MedBlend.MEDBLEND_OT_Select_Vdb_Temp_Dir()
        operator.directory = "/tmp"
        operator.filepath = ""
        reports = []
        operator.report = lambda level, message: reports.append((level, message))

        assert operator.execute(make_context(None)) == {"CANCELLED"}
        assert reports and "ERROR" in reports[0][0]

    def test_clear_resets_the_directory(self):
        prefs = FakePrefs(vdb_temp_dir="/somewhere")
        operator = MedBlend.MEDBLEND_OT_Clear_Vdb_Temp_Dir()
        assert operator.execute(make_context(prefs)) == {"FINISHED"}
        assert prefs.vdb_temp_dir == ""


class FakeVolume:
    type = "VOLUME"

    def __init__(self, name):
        self.name = name


class TestApplyPresetReporting:
    """The status bar shows the last report only, so failures must not be buried."""

    @staticmethod
    def _run(monkeypatch, results, volumes):
        calls = iter(results)

        def fake_apply(_obj, _preset, on_error=None, **_kwargs):
            outcome = next(calls)
            if outcome is None and on_error is not None:
                on_error("volume has no material slot")
            return outcome

        monkeypatch.setattr(MedBlend, "apply_volume_preset", fake_apply)

        operator = MedBlend.MEDBLEND_OT_Apply_Volume_Preset()
        operator.preset = "CT-Bone"
        operator.fit_mode = presets.FIT_AUTO
        operator.density_scale = 200.0
        operator.emission_strength = 1.0
        reports = []
        operator.report = lambda level, message: reports.append((set(level), message))

        context = type("_Ctx", (), {"selected_objects": volumes, "active_object": None})()
        return operator.execute(context), reports

    def test_full_success_reports_once_as_info(self, monkeypatch):
        result, reports = self._run(monkeypatch, ["mat", "mat"], [FakeVolume("a"), FakeVolume("b")])
        assert result == {"FINISHED"}
        assert len(reports) == 1
        assert reports[0][0] == {"INFO"}
        assert "2 volume(s)" in reports[0][1]

    def test_partial_failure_survives_in_the_final_report(self, monkeypatch):
        result, reports = self._run(monkeypatch, ["mat", None], [FakeVolume("a"), FakeVolume("b")])
        assert result == {"FINISHED"}
        # A trailing INFO used to overwrite the WARNING in the status bar.
        assert len(reports) == 1
        assert reports[0][0] == {"WARNING"}
        assert "1 skipped" in reports[0][1]
        assert "no material slot" in reports[0][1]

    def test_total_failure_cancels_with_the_reason(self, monkeypatch):
        result, reports = self._run(monkeypatch, [None], [FakeVolume("a")])
        assert result == {"CANCELLED"}
        assert reports[-1][0] == {"ERROR"}
        assert "no material slot" in reports[-1][1]
