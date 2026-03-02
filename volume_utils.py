"""Helpers for writing volume data to VDB."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence, Tuple

import bpy

from .ui_utils import show_message_box


def _get_vdb_temp_dir() -> Optional[Path]:
    addon = bpy.context.preferences.addons.get(__package__)
    if not addon:
        return None
    prefs = addon.preferences
    if not getattr(prefs, "vdb_temp_dir", ""):
        return None
    try:
        resolved = bpy.path.abspath(prefs.vdb_temp_dir)
        return Path(resolved)
    except Exception:
        return None


def resolve_temp_path(target_name: str, base_dir: Optional[Path] = None) -> Path:
    preferred_dir = _get_vdb_temp_dir()
    if preferred_dir:
        base_dir = preferred_dir
    else:
        base_dir = Path(base_dir) if base_dir else Path(bpy.app.tempdir or Path.cwd())

    try:
        base_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        show_message_box(
            f"Failed to create VDB directory '{base_dir}': {exc}",
            "Error",
            "ERROR",
        )
        base_dir = Path(bpy.app.tempdir or Path.cwd())
        base_dir.mkdir(parents=True, exist_ok=True)

    return base_dir / target_name


def _link_object_to_context_collection(obj: bpy.types.Object) -> None:
    collection = bpy.context.collection or bpy.context.scene.collection
    collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)


def _import_volume_data_api(output_path: Path) -> bpy.types.Object:
    """Import a VDB file using Blender data API to avoid context-sensitive operators."""

    volume_data = bpy.data.volumes.load(str(output_path))
    obj = bpy.data.objects.new(output_path.stem, volume_data)
    _link_object_to_context_collection(obj)
    return obj


def _import_volume_operator_fallback(output_path: Path) -> bpy.types.Object:
    """Fallback for Blender builds where data API loading is unavailable."""

    before_names = {obj.name for obj in bpy.data.objects}
    result = bpy.ops.object.volume_import(
        filepath=str(output_path),
        directory=str(output_path.parent),
        files=[{"name": output_path.name}],
    )
    if "FINISHED" not in result:
        raise RuntimeError("Volume import operator did not finish successfully")

    active_obj = bpy.context.view_layer.objects.active
    if active_obj and active_obj.name not in before_names:
        return active_obj

    # Fall back to matching by object type and expected base name.
    candidates = [obj for obj in bpy.data.objects if obj.name not in before_names and obj.type == "VOLUME"]
    if candidates:
        return candidates[-1]
    raise RuntimeError("Unable to resolve imported volume object from operator fallback")


def write_vdb_volume(
    array,
    spacing: Sequence[float],
    target_name: str,
    dicom_dir: Optional[Path] = None,
) -> Optional[Tuple[Path, bpy.types.Object]]:
    if len(spacing) != 3:
        show_message_box(
            f"Expected 3 spacing values (x, y, z), got {len(spacing)}.",
            "Error",
            "ERROR",
        )
        return None
    if any(value <= 0 for value in spacing):
        show_message_box(
            "Spacing values must be positive to create a VDB volume.",
            "Error",
            "ERROR",
        )
        return None

    try:
        import openvdb
    except Exception as exc:
        show_message_box(f"openvdb is not available: {exc}", "Missing Dependency", "ERROR")
        return None

    try:
        grid = openvdb.FloatGrid()
        grid.copyFromArray(array.astype(float))
        grid.transform = openvdb.createLinearTransform(
            [
                [spacing[0] / 1000.0, 0, 0, 0],
                [0, spacing[1] / 1000.0, 0, 0],
                [0, 0, spacing[2] / 1000.0, 0],
                [0, 0, 0, 1],
            ]
        )
        grid.gridClass = openvdb.GridClass.FOG_VOLUME
        grid.name = "density"

        output_path = resolve_temp_path(target_name, dicom_dir)
        openvdb.write(str(output_path), grid)

        try:
            imported_obj = _import_volume_data_api(output_path)
        except Exception:
            imported_obj = _import_volume_operator_fallback(output_path)

        return output_path, imported_obj
    except Exception as exc:
        show_message_box(f"Failed to create VDB volume: {exc}", "Error", "ERROR")
        return None
