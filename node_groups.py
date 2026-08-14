"""Helpers for loading shared geometry nodes and materials."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Sequence

import bpy

from .ui_utils import show_message_box


def _blend_library_path() -> Path:
    return Path(__file__).resolve().parent / "assets" / "MedBlend_Assets.blend"


def append_item_from_blend(file_path: Path, item_type: str, item_name: str) -> None:
    directory = str(file_path / item_type)
    bpy.ops.wm.append(directory=directory + os.sep, filename=item_name)


def _load_material(shader_name: str) -> Optional[bpy.types.Material]:
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
    return material


def _assign_material(obj: Optional[bpy.types.Object], material: bpy.types.Material) -> bool:
    if obj is None or obj.data is None or not hasattr(obj.data, "materials"):
        return False
    if not any(slot_material is material for slot_material in obj.data.materials):
        obj.data.materials.append(material)
    return True


def apply_dicom_shader(shader_name: str, obj: Optional[bpy.types.Object] = None) -> bool:
    """Attach the requested shader to ``obj``, appending the material when needed.

    ``obj`` defaults to the active object, but callers that just created an
    object should pass it explicitly - relying on the active object breaks when
    an import path leaves a different object selected.
    """

    material = _load_material(shader_name)
    if material is None:
        return False

    return _assign_material(obj if obj is not None else bpy.context.object, material)


def _set_material_color(material: bpy.types.Material, color: Sequence[float]) -> None:
    """Tint a material copy with an RT structure's display colour."""

    rgba = (float(color[0]), float(color[1]), float(color[2]), float(color[3]) if len(color) > 3 else 1.0)
    material.diffuse_color = rgba

    node_tree = getattr(material, "node_tree", None)
    if node_tree is None:
        return
    for node in node_tree.nodes:
        color_input = node.inputs.get("Color") if hasattr(node, "inputs") else None
        if color_input is not None and getattr(color_input, "type", "") == "RGBA" and not color_input.is_linked:
            color_input.default_value = rgba


def apply_structure_material(
    obj: Optional[bpy.types.Object],
    roi_name: str,
    color: Optional[Sequence[float]] = None,
    shader_name: str = "Structure Material",
) -> bool:
    """Assign a per-ROI copy of the structure material tinted with its colour.

    Sharing one material across every ROI makes each imported structure render
    identically, so ``ROIDisplayColor`` from the treatment planning system is
    baked into a copy instead.
    """

    base_material = _load_material(shader_name)
    if base_material is None:
        return False

    if color is None:
        return _assign_material(obj, base_material)

    material_name = f"{shader_name} - {roi_name}"
    material = bpy.data.materials.get(material_name)
    if material is None:
        try:
            material = base_material.copy()
            material.name = material_name
            _set_material_color(material, color)
        except Exception:
            material = base_material

    return _assign_material(obj, material)


def apply_proton_spots_geo_nodes(
    node_tree_name: str = "Proton_Spots",
    obj: Optional[bpy.types.Object] = None,
) -> Optional[bpy.types.Modifier]:
    """Ensure the proton geometry nodes modifier is present on ``obj``."""

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

    if obj is None:
        obj = bpy.context.active_object
    if obj is None:
        return None

    geomod = obj.modifiers.get("GeometryNodes")
    if not geomod:
        geomod = obj.modifiers.new("GeometryNodes", "NODES")

    geomod.node_group = node_group
    return geomod
