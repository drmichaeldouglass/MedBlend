"""Helpers for writing volume data to VDB."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence, Tuple

import bpy
import numpy as np
from mathutils import Matrix

from .ui_utils import show_message_box


def _default_temp_base_dir() -> Path:
    temp_dir = bpy.app.tempdir
    if temp_dir:
        return Path(temp_dir)

    cache_dir = getattr(bpy.app, "cachedir", "")
    if cache_dir:
        return Path(cache_dir)

    return Path.cwd()


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
        base_dir = Path(base_dir) if base_dir else _default_temp_base_dir()

    try:
        base_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        show_message_box(
            f"Failed to create VDB directory '{base_dir}': {exc}",
            "Error",
            "ERROR",
        )
        base_dir = _default_temp_base_dir()
        base_dir.mkdir(parents=True, exist_ok=True)

    return base_dir / target_name


def _link_object_to_context_collection(obj: bpy.types.Object) -> None:
    collection = bpy.context.collection or bpy.context.scene.collection
    collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)


def set_object_patient_transform(
    obj: bpy.types.Object,
    origin_mm: Sequence[float],
    slice_dir: Sequence[float],
    row_dir: Sequence[float],
    col_dir: Sequence[float],
) -> None:
    rot = Matrix(
        (
            (float(slice_dir[0]), float(row_dir[0]), float(col_dir[0]), 0.0),
            (float(slice_dir[1]), float(row_dir[1]), float(col_dir[1]), 0.0),
            (float(slice_dir[2]), float(row_dir[2]), float(col_dir[2]), 0.0),
            (0.0, 0.0, 0.0, 1.0),
        )
    )
    rot.translation = (
        float(origin_mm[0]) / 1000.0,
        float(origin_mm[1]) / 1000.0,
        float(origin_mm[2]) / 1000.0,
    )
    obj.matrix_world = rot


def align_object_to_ct_frame(
    obj: bpy.types.Object,
    ct_obj: bpy.types.Object,
    origin_mm: Sequence[float],
    basis_mm: Sequence[Sequence[float]],
    spacing_mm: Sequence[float],
) -> bool:
    ct_basis_flat = ct_obj.get("medblend_ct_basis_mm")
    if not ct_basis_flat or len(ct_basis_flat) != 9:
        return False

    try:
        ct_basis = np.asarray(ct_basis_flat, dtype=float).reshape((3, 3))
        ct_origin = np.asarray(ct_obj.get("medblend_ct_origin_mm", [0.0, 0.0, 0.0]), dtype=float)
        ct_spacing = np.asarray(ct_obj.get("medblend_ct_spacing_mm", [1.0, 1.0, 1.0]), dtype=float)
        source_origin = np.asarray(origin_mm, dtype=float)
        source_basis = np.asarray(basis_mm, dtype=float).reshape((3, 3))
        source_spacing = np.asarray(spacing_mm, dtype=float)
        if np.any(source_spacing <= 0) or np.any(ct_spacing <= 0):
            return False

        patient_to_world = np.diag(ct_spacing / 1000.0) @ np.linalg.inv(ct_basis)
        source_scale = np.diag(source_spacing / 1000.0)
        linear = patient_to_world @ source_basis @ np.linalg.inv(source_scale)
        translation = patient_to_world @ (source_origin - ct_origin)

        matrix = Matrix(
            (
                (float(linear[0, 0]), float(linear[0, 1]), float(linear[0, 2]), 0.0),
                (float(linear[1, 0]), float(linear[1, 1]), float(linear[1, 2]), 0.0),
                (float(linear[2, 0]), float(linear[2, 1]), float(linear[2, 2]), 0.0),
                (0.0, 0.0, 0.0, 1.0),
            )
        )
        matrix.translation = tuple(float(value) for value in translation)
        obj.matrix_world = matrix
    except Exception:
        return False

    return True


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


def _import_openvdb_module():
    last_exc = None
    for module_name in ("openvdb", "pyopenvdb"):
        try:
            return __import__(module_name)
        except Exception as exc:
            last_exc = exc

    raise ModuleNotFoundError(
        "Neither 'openvdb' nor 'pyopenvdb' could be imported. "
        "Ensure Blender ships a compatible OpenVDB Python module."
    ) from last_exc


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
        openvdb = _import_openvdb_module()
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
