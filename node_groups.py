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


# Blender truncates datablock names past this length. A truncated name would
# never match the cache lookup below, so every re-import would copy the
# material again and the file would accumulate one copy per import.
_MAX_DATABLOCK_NAME = 63


def _rgba(color: Sequence[float]) -> tuple[float, float, float, float]:
    return (
        float(color[0]),
        float(color[1]),
        float(color[2]),
        float(color[3]) if len(color) > 3 else 1.0,
    )


def _set_material_color(material: bpy.types.Material, color: Sequence[float]) -> None:
    """Tint a material copy with an RT structure's display colour."""

    rgba = _rgba(color)
    material.diffuse_color = rgba

    node_tree = getattr(material, "node_tree", None)
    if node_tree is None:
        return
    for node in node_tree.nodes:
        color_input = node.inputs.get("Color") if hasattr(node, "inputs") else None
        if color_input is not None and getattr(color_input, "type", "") == "RGBA" and not color_input.is_linked:
            color_input.default_value = rgba


def _material_has_color(material: bpy.types.Material, rgba: Sequence[float]) -> bool:
    existing = getattr(material, "diffuse_color", None)
    if existing is None:
        return False
    try:
        return len(existing) >= 4 and all(
            abs(float(a) - float(b)) <= 1e-6 for a, b in zip(rgba, existing)
        )
    except (TypeError, ValueError):
        return False


def _tint_name(base_name: str, counter: int) -> str:
    suffix = "" if counter == 0 else f"_{counter}"
    return base_name[: _MAX_DATABLOCK_NAME - len(suffix)] + suffix


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

    A cached tint is only reused when its colour still matches. Two structure
    sets can use the same ROI name with different display colours, and reusing
    the datablock on name alone gave the second import the first one's colour -
    and retinting it in place would have recoloured the structure already in
    the scene.
    """

    base_material = _load_material(shader_name)
    if base_material is None:
        return False

    if color is None:
        return _assign_material(obj, base_material)

    rgba = _rgba(color)
    base_name = f"{shader_name} - {roi_name}"
    material = base_material
    for counter in range(100):
        candidate = _tint_name(base_name, counter)
        existing = bpy.data.materials.get(candidate)
        if existing is None:
            try:
                material = base_material.copy()
                material.name = candidate
                _set_material_color(material, rgba)
            except Exception:
                material = base_material
            break
        if _material_has_color(existing, rgba):
            material = existing
            break

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
