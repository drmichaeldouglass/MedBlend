"""Blender specific helper functions."""

from __future__ import annotations

import bpy
from bpy.types import Mesh, Object


def add_vertex_float_attributes(mesh: Mesh, names: list[str]) -> None:
    """Ensure that *mesh* has float point-domain attributes for each entry in *names*."""

    for name in names:
        attribute_name = name or "attribute"
        if attribute_name not in mesh.attributes:
            mesh.attributes.new(name=attribute_name, type='FLOAT', domain='POINT')


def create_mesh_object(mesh: Mesh, name: str, *, collection: bpy.types.Collection | None = None) -> Object:
    """Create and link a new object that owns *mesh*."""

    collection = collection or bpy.context.collection

    for obj in bpy.context.selected_objects:
        obj.select_set(False)

    obj = bpy.data.objects.new(name=name, object_data=mesh)
    collection.objects.link(obj)

    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    return obj


def active_object() -> Object | None:
    """Return the active object or ``None`` when unavailable."""

    return bpy.context.view_layer.objects.active


__all__ = [
    "active_object",
    "add_vertex_float_attributes",
    "create_mesh_object",
]
