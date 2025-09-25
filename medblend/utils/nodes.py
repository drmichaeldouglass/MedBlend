"""Helpers for working with linked Blender data blocks."""

from __future__ import annotations

import bpy

from ..constants import ASSETS_DIR
from .blender import active_object

_ASSET_LIBRARY = ASSETS_DIR / "MedBlend_Assets.blend"


def _append_data_block(block_type: str, name: str) -> None:
    if not _ASSET_LIBRARY.exists():
        raise FileNotFoundError(f"Missing MedBlend asset library: {_ASSET_LIBRARY}")

    directory = _ASSET_LIBRARY.as_posix() + f"/{block_type}/"
    bpy.ops.wm.append(directory=directory, filename=name)


def apply_material(name: str) -> bool:
    """Append *name* from the asset library and assign it to the active object."""

    obj = active_object()
    if obj is None or not hasattr(obj.data, "materials"):
        return False

    material = bpy.data.materials.get(name)
    if material is None:
        try:
            _append_data_block("Material", name)
        except Exception:
            return False
        material = bpy.data.materials.get(name)
        if material is None:
            return False

    if material not in obj.data.materials:
        obj.data.materials.append(material)
    return True


def apply_geometry_nodes(node_tree_name: str) -> bool:
    """Assign the *node_tree_name* geometry node group to the active object."""

    obj = active_object()
    if obj is None:
        return False

    node_group = bpy.data.node_groups.get(node_tree_name)
    if node_group is None:
        try:
            _append_data_block("NodeTree", node_tree_name)
        except Exception:
            return False
        node_group = bpy.data.node_groups.get(node_tree_name)
        if node_group is None:
            return False

    modifier = obj.modifiers.get(node_tree_name)
    if modifier is None:
        modifier = obj.modifiers.new(node_tree_name, 'NODES')

    modifier.node_group = node_group
    return True


__all__ = [
    "apply_geometry_nodes",
    "apply_material",
]
