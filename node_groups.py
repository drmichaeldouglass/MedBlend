"""Helpers for loading shared geometry nodes and materials."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import bpy

from .ui_utils import show_message_box


def _blend_library_path() -> Path:
    return Path(__file__).resolve().parent / "assets" / "MedBlend_Assets.blend"


def append_item_from_blend(file_path: Path, item_type: str, item_name: str) -> None:
    directory = str(file_path / item_type)
    bpy.ops.wm.append(directory=directory + os.sep, filename=item_name)


def apply_dicom_shader(shader_name: str) -> bool:
    """Attach the requested shader to the active object, appending when needed."""

    if shader_name not in bpy.data.materials:
        try:
            append_item_from_blend(_blend_library_path(), "Material", shader_name)
        except Exception:
            pass

    material = bpy.data.materials.get(shader_name)
    if material is None:
        show_message_box(
            f"Material '{shader_name}' could not be loaded from the MedBlend asset library.",
            "Warning",
            "ERROR",
        )
        return False

    obj = bpy.context.object
    if obj and obj.data and hasattr(obj.data, "materials"):
        if not any(slot_material is material for slot_material in obj.data.materials):
            obj.data.materials.append(material)
        return True

    return False


def apply_proton_spots_geo_nodes(node_tree_name: str = "Proton_Spots") -> Optional[bpy.types.Modifier]:
    """Ensure the proton geometry nodes modifier is present on the active object."""

    if node_tree_name not in bpy.data.node_groups:
        try:
            append_item_from_blend(_blend_library_path(), "NodeTree", node_tree_name)
        except Exception:
            pass

    node_group = bpy.data.node_groups.get(node_tree_name)
    if node_group is None:
        show_message_box(
            f"Node group '{node_tree_name}' could not be loaded from the MedBlend asset library.",
            "Warning",
            "ERROR",
        )
        return None

    obj = bpy.context.active_object
    if obj is None:
        return None

    geomod = obj.modifiers.get("GeometryNodes")
    if not geomod:
        geomod = obj.modifiers.new("GeometryNodes", "NODES")

    geomod.node_group = node_group
    return geomod
