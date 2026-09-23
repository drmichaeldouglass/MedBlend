"""Helpers for loading shared geometry nodes and materials."""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Optional, Sequence

import bpy

from .ui_utils import show_message_box

#: Group input pairs the shipped image, dose and spot materials expose for
#: their window. Imported data keeps its own units - Hounsfield units, absolute
#: dose in Gy, spot meterset weights - so the material has to be told the range
#: they cover before its colour ramp, which is addressed by ``0 - 1``, means
#: anything.
_WINDOW_INPUT_PAIRS = (
    ("Min HU", "Max HU"),
    ("Min Dose", "Max Dose"),
    ("Min Spot Weight", "Max Spot Weight"),
)

#: Custom property recording the window a material copy was built for.
_WINDOW_PROPERTY = "medblend_material_window"


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


# Blender truncates datablock names past this length. A truncated name would
# never match the cache lookup below, so every re-import would copy the
# material again and the file would accumulate one copy per import.
_MAX_DATABLOCK_NAME = 63


def _variant_name(base_name: str, counter: int) -> str:
    """Name a per-window or per-colour copy so the cache lookup can find it."""

    suffix = "" if counter == 0 else f"_{counter}"
    return base_name[: _MAX_DATABLOCK_NAME - len(suffix)] + suffix


def _socket(node, name: str):
    """Return an input socket by name, or ``None`` when the node has no such input."""

    inputs = getattr(node, "inputs", None)
    if inputs is None:
        return None
    try:
        return inputs[name]
    except (KeyError, TypeError, IndexError):
        return None


def _valid_window(data_range: Optional[Sequence[float]]) -> Optional[tuple[float, float]]:
    if data_range is None:
        return None
    try:
        low, high = float(data_range[0]), float(data_range[1])
    except (TypeError, ValueError, IndexError, KeyError):
        return None
    if not math.isfinite(low) or not math.isfinite(high) or high <= low:
        return None
    return low, high


def _window_sockets(material: bpy.types.Material) -> list:
    """Every writable window input pair among the material's nodes.

    A pair driven by a link is skipped: the user is setting the window
    themselves, and a default behind a link does nothing visible anyway.
    """

    node_tree = getattr(material, "node_tree", None)
    if node_tree is None:
        return []

    pairs = []
    for node in getattr(node_tree, "nodes", ()):
        for names in _WINDOW_INPUT_PAIRS:
            sockets = [_socket(node, name) for name in names]
            if any(socket is None for socket in sockets):
                continue
            if any(getattr(socket, "is_linked", False) for socket in sockets):
                continue
            pairs.append(sockets)
    return pairs


def _set_material_window(material: bpy.types.Material, window: Sequence[float]) -> None:
    """Point every writable window input in ``material`` at ``window``."""

    low, high = float(window[0]), float(window[1])
    for low_socket, high_socket in _window_sockets(material):
        low_socket.default_value = low
        high_socket.default_value = high
    material[_WINDOW_PROPERTY] = [low, high]


def _material_has_window(material: bpy.types.Material, window: Sequence[float]) -> bool:
    stored = material.get(_WINDOW_PROPERTY) if hasattr(material, "get") else None
    try:
        if stored is None or len(stored) != 2:
            return False
        return all(
            abs(float(a) - float(b)) <= 1e-6
            for a, b in zip(window, stored, strict=True)
        )
    except (TypeError, ValueError):
        return False


def _fill_zero_inputs(material: bpy.types.Material, values: dict[str, float]) -> None:
    """Set each named, unlinked input that is still at zero to its value.

    An input the user has already given a value in their own copy of the
    asset is left as they set it.
    """

    node_tree = getattr(material, "node_tree", None)
    if node_tree is None:
        return
    for node in getattr(node_tree, "nodes", ()):
        for name, value in values.items():
            socket = _socket(node, name)
            if socket is None or getattr(socket, "is_linked", False):
                continue
            try:
                if float(socket.default_value) <= 0.0:
                    socket.default_value = float(value)
            except (TypeError, ValueError):
                continue


def _windowed_material(
    base_material: bpy.types.Material,
    shader_name: str,
    window: tuple[float, float],
    zero_input_defaults: Optional[dict[str, float]] = None,
) -> bpy.types.Material:
    """Return a copy of ``base_material`` whose window spans ``window``.

    Two scans rarely cover the same range of values, so the window cannot be
    written into the shared material - that would rewindow every volume
    already using it. A copy per window is cached by name and reused, the same
    way per-ROI structure tints are.

    ``zero_input_defaults`` fills in inputs the asset leaves at zero on the
    new copy, via :func:`_fill_zero_inputs`.
    """

    # An edited or replaced asset may have nothing to window. Checking before
    # copying keeps a stray datablock out of the file.
    if not _window_sockets(base_material):
        return base_material

    low, high = window
    base_name = f"{shader_name} - {low:g} to {high:g}"
    for counter in range(100):
        candidate = _variant_name(base_name, counter)
        existing = bpy.data.materials.get(candidate)
        if existing is None:
            break
        if _material_has_window(existing, window):
            return existing
    else:
        return base_material

    try:
        material = base_material.copy()
        material.name = candidate
        _set_material_window(material, window)
        if zero_input_defaults:
            _fill_zero_inputs(material, zero_input_defaults)
    except Exception:
        return base_material

    return material


def apply_dicom_shader(
    shader_name: str,
    obj: Optional[bpy.types.Object] = None,
    data_range: Optional[Sequence[float]] = None,
    zero_input_defaults: Optional[dict[str, float]] = None,
) -> bool:
    """Attach the requested shader to ``obj``, appending the material when needed.

    ``obj`` defaults to the active object, but callers that just created an
    object should pass it explicitly - relying on the active object breaks when
    an import path leaves a different object selected.

    ``data_range`` is the span of values the volume's voxels cover. When given,
    a copy of the material windowed onto that range is assigned instead of the
    shared one, so a volume in Hounsfield units or Gy renders without the user
    having to type its range into the shader. ``zero_input_defaults`` names
    inputs the windowed copy should get when the asset leaves them at zero.
    """

    material = _load_material(shader_name)
    if material is None:
        return False

    window = _valid_window(data_range)
    if window is not None:
        material = _windowed_material(material, shader_name, window, zero_input_defaults)

    return _assign_material(obj if obj is not None else bpy.context.object, material)


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
            abs(float(a) - float(b)) <= 1e-6
            for a, b in zip(rgba, existing, strict=True)
        )
    except (TypeError, ValueError):
        return False


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
        candidate = _variant_name(base_name, counter)
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


#: Radius, in metres, of the heaviest spot in an imported plan. The node
#: group draws each spot at ``spot_weight * Spot Size``, and the asset's Spot
#: Size (0.1 mm per unit weight) was tuned on a plan whose heaviest spot
#: weighed 12.97, so this keeps that look whatever units the plan's meterset
#: weights are in.
MAX_SPOT_RADIUS = 12.97 * 1e-4


def _windowed_spot_node_group(node_group, window: tuple[float, float]):
    """Return a copy of ``node_group`` whose spot material spans ``window``.

    The Spot Material is chosen by a Set Material node inside the node group
    rather than on the object, so windowing it means pointing a copy of the
    node group at a windowed copy of the material. Both are cached by window,
    the same way windowed image materials are.
    """

    replacements = {}
    for node in getattr(node_group, "nodes", ()):
        if getattr(node, "bl_idname", "") != "GeometryNodeSetMaterial":
            continue
        socket = _socket(node, "Material")
        material = getattr(socket, "default_value", None)
        if material is None or getattr(socket, "is_linked", False):
            continue
        windowed = _windowed_material(material, material.name, window)
        if windowed is not material:
            replacements[node.name] = windowed
    if not replacements:
        return node_group

    low, high = window
    base_name = f"{node_group.name} - {low:g} to {high:g}"
    for counter in range(100):
        candidate = _variant_name(base_name, counter)
        existing = bpy.data.node_groups.get(candidate)
        if existing is None:
            break
        if _material_has_window(existing, window):
            return existing
    else:
        return node_group

    try:
        windowed_group = node_group.copy()
        windowed_group.name = candidate
        for node_name, material in replacements.items():
            windowed_group.nodes[node_name].inputs["Material"].default_value = material
        windowed_group[_WINDOW_PROPERTY] = [float(low), float(high)]
    except Exception:
        return node_group
    return windowed_group


def _set_modifier_input(modifier, name: str, value: float) -> bool:
    """Set a geometry nodes modifier input by its interface name."""

    interface = getattr(getattr(modifier, "node_group", None), "interface", None)
    for item in getattr(interface, "items_tree", ()):
        if getattr(item, "in_out", None) != "INPUT" or getattr(item, "name", None) != name:
            continue
        try:
            modifier[item.identifier] = float(value)
        except Exception:
            return False
        return True
    return False


def apply_proton_spots_geo_nodes(
    node_tree_name: str = "Proton_Spots",
    obj: Optional[bpy.types.Object] = None,
    weight_range: Optional[Sequence[float]] = None,
) -> Optional[bpy.types.Modifier]:
    """Ensure the proton geometry nodes modifier is present on ``obj``.

    ``weight_range`` is the span of spot meterset weights in the plan. When
    given, the spot colours are windowed onto it and the Spot Size is scaled
    so the heaviest spot is drawn at :data:`MAX_SPOT_RADIUS`. The asset's
    fixed window and size otherwise only suit plans whose weights happen to
    be in the same units as the one it was tuned on.
    """

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

    window = _valid_window(weight_range)
    if window is not None:
        node_group = _windowed_spot_node_group(node_group, window)

    geomod = obj.modifiers.get("GeometryNodes")
    if not geomod:
        geomod = obj.modifiers.new("GeometryNodes", "NODES")

    geomod.node_group = node_group
    if window is not None:
        _set_modifier_input(geomod, "Spot Size", MAX_SPOT_RADIUS / window[1])
    return geomod
