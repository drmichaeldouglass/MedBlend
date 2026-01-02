"""Helpers for loading shared geometry nodes and materials."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import bpy


def _blend_library_path() -> Path:
    current_path = Path(bpy.path.abspath(os.path.dirname(__file__)))
    return current_path / "assets" / "MedBlend_Assets.blend"


def append_item_from_blend(file_path: Path, item_type: str, item_name: str) -> None:
    directory = str(file_path / item_type)
    bpy.ops.wm.append(directory=directory + os.sep, filename=item_name)


def apply_dicom_shader(shader_name: str) -> bool:
    """Attach the requested shader to the active object, appending when needed."""

    blend_path = _blend_library_path()
    if shader_name not in bpy.data.materials:
        append_item_from_blend(blend_path, "Material", shader_name)

    obj = bpy.context.object
    if obj and obj.data and hasattr(obj.data, "materials"):
        obj.data.materials.append(bpy.data.materials[shader_name])
        return True

    return False


def apply_proton_spots_geo_nodes(node_tree_name: str = "Proton_Spots") -> Optional[bpy.types.Modifier]:
    """Ensure the proton geometry nodes modifier is present on the active object."""

    blend_path = _blend_library_path()
    if node_tree_name not in bpy.data.node_groups:
        append_item_from_blend(blend_path, "NodeTree", node_tree_name)

    obj = bpy.context.active_object
    if obj is None:
        return None

    geomod = obj.modifiers.get("GeometryNodes")
    if not geomod:
        geomod = obj.modifiers.new("GeometryNodes", "NODES")

    geomod.node_group = bpy.data.node_groups.get(node_tree_name)
    return geomod

