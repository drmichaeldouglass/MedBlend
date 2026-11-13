"""Generated VDB files must outlive the Blender session that made them."""

from __future__ import annotations

from pathlib import Path

import bpy
import pytest

import MedBlend
from MedBlend import volume_utils


class FakeVolume:
    def __init__(self, filepath, generated=True, library=None):
        self.name = Path(str(filepath)).stem
        self.filepath = str(filepath)
        self.library = library
        self._props = {volume_utils.GENERATED_VDB_KEY: True} if generated else {}

    def get(self, key, default=None):
        return self._props.get(key, default)


@pytest.fixture
def session(tmp_path, monkeypatch):
    """A session temp directory and a separate place to save the scene."""

    temp_dir = tmp_path / "blender_session"
    temp_dir.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    volumes = []
    monkeypatch.setattr(bpy.app, "tempdir", str(temp_dir), raising=False)
    monkeypatch.setattr(bpy.data, "volumes", volumes, raising=False)
    monkeypatch.setattr(bpy.data, "filepath", "", raising=False)
    monkeypatch.setattr(volume_utils, "_get_vdb_temp_dir", lambda: None)

    def add(name, where=temp_dir, **kwargs):
        path = where / name
        path.write_bytes(name.encode())
        volume = FakeVolume(path, **kwargs)
        volumes.append(volume)
        return volume

    return type("Session", (), {"temp": temp_dir, "project": project, "add": staticmethod(add)})


class TestRelocationOnSave:
    def test_session_files_are_copied_beside_the_blend_and_repointed(self, session):
        ct = session.add("CT.vdb")
        dose = session.add("dose.vdb")
        blend = session.project / "plan.blend"

        moved = volume_utils.relocate_session_volumes(str(blend))

        target = session.project / "plan_vdb"
        assert sorted(path.name for path in moved) == ["CT.vdb", "dose.vdb"]
        assert Path(ct.filepath) == target / "CT.vdb"
        assert Path(dose.filepath) == target / "dose.vdb"
        assert (target / "CT.vdb").read_bytes() == b"CT.vdb"

    def test_a_second_save_copies_nothing_more(self, session):
        session.add("CT.vdb")
        blend = session.project / "plan.blend"
        volume_utils.relocate_session_volumes(str(blend))

        assert volume_utils.relocate_session_volumes(str(blend)) == []
        assert [p.name for p in (session.project / "plan_vdb").iterdir()] == ["CT.vdb"]

    def test_an_existing_file_of_the_same_name_is_not_overwritten(self, session):
        target = session.project / "plan_vdb"
        target.mkdir()
        (target / "CT.vdb").write_bytes(b"earlier import")
        ct = session.add("CT.vdb")

        volume_utils.relocate_session_volumes(str(session.project / "plan.blend"))

        assert (target / "CT.vdb").read_bytes() == b"earlier import"
        assert Path(ct.filepath) == target / "CT_1.vdb"

    def test_volumes_sharing_one_file_share_one_copy(self, session):
        first = session.add("CT.vdb")
        second = FakeVolume(first.filepath)
        bpy.data.volumes.append(second)

        moved = volume_utils.relocate_session_volumes(str(session.project / "plan.blend"))

        assert len(moved) == 1
        assert first.filepath == second.filepath

    def test_files_medblend_did_not_write_are_left_alone(self, session):
        foreign = session.add("smoke.vdb", generated=False)
        original = foreign.filepath

        assert volume_utils.relocate_session_volumes(str(session.project / "plan.blend")) == []
        assert foreign.filepath == original

    def test_files_already_outside_the_session_directory_stay_put(self, session):
        persistent = session.add("CT.vdb", where=session.project)
        original = persistent.filepath

        assert volume_utils.relocate_session_volumes(str(session.project / "plan.blend")) == []
        assert persistent.filepath == original

    def test_a_save_into_the_session_directory_relocates_nothing(self, session):
        ct = session.add("CT.vdb")
        original = ct.filepath

        assert volume_utils.relocate_session_volumes(str(session.temp / "quit.blend")) == []
        assert ct.filepath == original

    def test_a_missing_source_file_does_not_fail_the_save(self, session):
        ct = session.add("CT.vdb")
        Path(ct.filepath).unlink()
        original = ct.filepath

        assert volume_utils.relocate_session_volumes(str(session.project / "plan.blend")) == []
        assert ct.filepath == original

    def test_a_copy_failure_is_reported_and_the_rest_still_move(self, session, monkeypatch):
        session.add("CT.vdb")
        dose = session.add("dose.vdb")
        messages = []
        monkeypatch.setattr(
            volume_utils, "show_message_box", lambda message, *_a: messages.append(message)
        )
        real_copy = volume_utils.shutil.copy2

        def flaky_copy(source, destination):
            if Path(source).name == "CT.vdb":
                raise OSError("disk full")
            return real_copy(source, destination)

        monkeypatch.setattr(volume_utils.shutil, "copy2", flaky_copy)

        moved = volume_utils.relocate_session_volumes(str(session.project / "plan.blend"))

        assert [path.name for path in moved] == ["dose.vdb"]
        assert Path(dose.filepath).parent == session.project / "plan_vdb"
        assert len(messages) == 1 and "disk full" in messages[0]


class TestWhereNewVolumesAreWritten:
    def test_an_unsaved_scene_uses_the_session_directory(self, session):
        assert volume_utils.resolve_temp_path("CT.vdb") == session.temp / "CT.vdb"

    def test_a_saved_scene_writes_beside_the_blend(self, session, monkeypatch):
        monkeypatch.setattr(bpy.data, "filepath", str(session.project / "plan.blend"))

        assert volume_utils.resolve_temp_path("CT.vdb") == session.project / "plan_vdb" / "CT.vdb"

    def test_the_preference_directory_wins_over_both(self, session, monkeypatch, tmp_path):
        chosen = tmp_path / "chosen"
        monkeypatch.setattr(bpy.data, "filepath", str(session.project / "plan.blend"))
        monkeypatch.setattr(volume_utils, "_get_vdb_temp_dir", lambda: chosen)

        assert volume_utils.resolve_temp_path("CT.vdb") == chosen / "CT.vdb"


class TestSaveHandlerRegistration:
    def test_register_installs_the_handler_once_and_unregister_removes_it(self, monkeypatch):
        handlers = []
        monkeypatch.setattr(bpy.app.handlers, "save_pre", handlers)

        MedBlend.register()
        MedBlend.register()
        assert handlers == [MedBlend._relocate_volumes_on_save]

        MedBlend.unregister()
        assert handlers == []

    def test_the_handler_never_raises_into_the_save(self, monkeypatch):
        def boom(_path):
            raise RuntimeError("nope")

        monkeypatch.setattr(MedBlend, "relocate_session_volumes", boom)
        MedBlend._relocate_volumes_on_save("/somewhere/plan.blend", None)
