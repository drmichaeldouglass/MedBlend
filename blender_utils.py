"""Small Blender data helpers shared by the import operators."""

from __future__ import annotations

import bpy


def add_data_fields(mesh, data_fields):
    """Add float point attributes to ``mesh``.

    Adapted from https://github.com/simonbroggi/blender_spreadsheet_import
    """

    for data_field in data_fields:
        name = data_field if data_field else "empty_key_string"
        if name in mesh.attributes:
            continue
        mesh.attributes.new(name=name, type="FLOAT", domain="POINT")


def create_object(mesh, name):
    """Create an object for ``mesh`` and make it the sole active selection.

    Selection and the active object are a convenience. Both can be refused -
    the context has no selection outside a 3D viewport, and an object linked
    into a collection excluded from the view layer cannot be made active - and
    neither is a reason to fail an import whose object already exists.
    """

    for other in list(getattr(bpy.context, "selected_objects", None) or []):
        try:
            other.select_set(False)
        except (RuntimeError, ReferenceError):
            # Objects outside the active view layer cannot be deselected.
            continue

    obj = bpy.data.objects.new(name, mesh)
    collection = bpy.context.collection or bpy.context.scene.collection
    collection.objects.link(obj)
    try:
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
    except (RuntimeError, ReferenceError, AttributeError):
        pass
    return obj
