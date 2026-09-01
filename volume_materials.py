"""Build Blender volume materials from the Slicer-style presets."""

from __future__ import annotations

from typing import Callable, Optional, Sequence

import bpy

from . import presets as preset_lib
from .presets import FIT_AUTO, VolumePreset
from .ui_utils import show_message_box

#: Blender truncates datablock names past this length, so a cache lookup on a
#: truncated name would never match and every apply would build a new copy.
_MAX_DATABLOCK_NAME = 63

_MATERIAL_PREFIX = "MedBlend"

#: Extinction in 1/m at an opacity of 1. Volumes are imported in metres, so a
#: 300 mm patient at this scale is thoroughly opaque where the preset is
#: solid while still letting internal structure show through.
DEFAULT_DENSITY_SCALE = 200.0

#: Emissive volumes read immediately in both EEVEE and Cycles without the user
#: having to add a light, which is how the same preset looks in Slicer.
DEFAULT_EMISSION_STRENGTH = 1.0

_FLOAT_TOLERANCE = 1e-6


def _linear_rgba(color: Sequence[float]) -> tuple[float, float, float, float]:
    red, green, blue = (preset_lib.srgb_to_linear(float(value)) for value in color[:3])
    alpha = float(color[3]) if len(color) > 3 else 1.0
    return red, green, blue, alpha


def _fill_color_ramp(ramp, stops: Sequence[tuple[float, Sequence[float]]], to_rgba) -> None:
    """Replace a colour ramp's elements with ``stops``.

    A ramp must keep at least one element, so the first stop is written into
    the element that is already there and the rest are appended in order.
    """

    elements = ramp.elements
    while len(elements) > 1:
        elements.remove(elements[len(elements) - 1])

    first_position, first_values = stops[0]
    elements[0].position = first_position
    elements[0].color = to_rgba(first_values)

    for position, values in stops[1:]:
        element = elements.new(position)
        element.color = to_rgba(values)


def _color_stop_to_rgba(values: Sequence[float]) -> tuple[float, float, float, float]:
    return _linear_rgba(values)


def _opacity_stop_to_rgba(values: Sequence[float]) -> tuple[float, float, float, float]:
    # The opacity function is a scalar, not a colour, so it is not colour
    # managed. It is written into both the greyscale colour and the alpha so
    # the ramp reads correctly in the shader editor while the node tree takes
    # the exact value from the Alpha output.
    alpha = float(values[0])
    return alpha, alpha, alpha, alpha


def build_preset_node_tree(
    material: bpy.types.Material,
    preset: VolumePreset,
    window: Sequence[float],
    data_range: Sequence[float],
    density_scale: float,
    emission_strength: float,
) -> None:
    """Wire ``material`` up as a volume shader driven by ``preset``.

    The imported grid holds the values DICOM stored - Hounsfield units for a
    CT - while a colour ramp is addressed by ``0 - 1``. Both transfer
    functions are resampled onto that axis over ``window``, and the Map Range
    node in front of them normalises voxel values onto it by mapping
    ``data_range`` across. That node is also the window control: narrowing it
    is the equivalent of Slicer's shift slider.
    """

    low, high = float(window[0]), float(window[1])
    data_low, data_high = float(data_range[0]), float(data_range[1])

    material.use_nodes = True
    tree = material.node_tree
    nodes = tree.nodes
    links = tree.links
    nodes.clear()

    volume_info = nodes.new("ShaderNodeVolumeInfo")
    volume_info.location = (-960, 0)

    window_node = nodes.new("ShaderNodeMapRange")
    window_node.location = (-760, 0)
    window_node.label = "Window"
    window_node.name = "Window"
    window_node.clamp = True
    window_node.inputs["From Min"].default_value = data_low
    window_node.inputs["From Max"].default_value = data_high
    window_node.inputs["To Min"].default_value = 0.0
    window_node.inputs["To Max"].default_value = 1.0

    color_ramp = nodes.new("ShaderNodeValToRGB")
    color_ramp.location = (-520, 200)
    color_ramp.label = "Color Transfer"
    color_ramp.name = "Color Transfer"
    color_ramp.color_ramp.color_mode = "RGB"
    color_ramp.color_ramp.interpolation = "LINEAR"
    _fill_color_ramp(
        color_ramp.color_ramp,
        preset_lib.resample(preset.color, low, high),
        _color_stop_to_rgba,
    )

    opacity_ramp = nodes.new("ShaderNodeValToRGB")
    opacity_ramp.location = (-520, -180)
    opacity_ramp.label = "Scalar Opacity"
    opacity_ramp.name = "Scalar Opacity"
    opacity_ramp.color_ramp.color_mode = "RGB"
    opacity_ramp.color_ramp.interpolation = "LINEAR"
    _fill_color_ramp(
        opacity_ramp.color_ramp,
        preset_lib.resample(preset.opacity, low, high),
        _opacity_stop_to_rgba,
    )

    density = nodes.new("ShaderNodeMath")
    density.location = (-180, -180)
    density.label = "Density Scale"
    density.name = "Density Scale"
    density.operation = "MULTIPLY"
    density.inputs[1].default_value = float(density_scale)

    emission = nodes.new("ShaderNodeVectorMath")
    emission.location = (-180, 200)
    emission.label = "Emission Color"
    emission.name = "Emission Color"
    emission.operation = "SCALE"

    principled = nodes.new("ShaderNodeVolumePrincipled")
    principled.location = (120, 0)
    # Principled Volume multiplies its Density input by the named grid, which
    # would apply the raw voxel value on top of the opacity function.
    principled.inputs["Density Attribute"].default_value = ""
    principled.inputs["Emission Strength"].default_value = float(emission_strength)

    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (400, 0)

    links.new(volume_info.outputs["Density"], window_node.inputs["Value"])
    links.new(window_node.outputs["Result"], color_ramp.inputs["Fac"])
    links.new(window_node.outputs["Result"], opacity_ramp.inputs["Fac"])
    links.new(opacity_ramp.outputs["Alpha"], density.inputs[0])
    # Emission is not scaled by density in Cycles, so it is multiplied by the
    # opacity here - otherwise the whole bounding box would glow.
    links.new(color_ramp.outputs["Color"], emission.inputs[0])
    links.new(opacity_ramp.outputs["Alpha"], emission.inputs["Scale"])
    links.new(color_ramp.outputs["Color"], principled.inputs["Color"])
    links.new(emission.outputs["Vector"], principled.inputs["Emission Color"])
    links.new(density.outputs["Value"], principled.inputs["Density"])
    links.new(principled.outputs["Volume"], output.inputs["Volume"])


def _tag_material(
    material: bpy.types.Material,
    preset: VolumePreset,
    window: Sequence[float],
    data_range: Sequence[float],
    density_scale: float,
    emission_strength: float,
) -> None:
    """Record what the material was built from, for reuse and for the user.

    Slicer's Phong terms have no counterpart in Blender's physically based
    volume shader, so they are stored alongside rather than wired in - they
    still tell you how the preset was meant to be lit.
    """

    material["medblend_preset"] = preset.name
    material["medblend_preset_window"] = [float(window[0]), float(window[1])]
    material["medblend_preset_data_range"] = [float(data_range[0]), float(data_range[1])]
    material["medblend_preset_density_scale"] = float(density_scale)
    material["medblend_preset_emission_strength"] = float(emission_strength)
    material["medblend_slicer_ambient"] = preset.ambient
    material["medblend_slicer_diffuse"] = preset.diffuse
    material["medblend_slicer_specular"] = preset.specular
    material["medblend_slicer_specular_power"] = preset.specular_power
    material["medblend_slicer_shade"] = preset.shade


def _matches(
    material: bpy.types.Material,
    preset: VolumePreset,
    window: Sequence[float],
    data_range: Sequence[float],
    density_scale: float,
    emission_strength: float,
) -> bool:
    if material.get("medblend_preset") != preset.name:
        return False

    stored_window = material.get("medblend_preset_window")
    stored_data_range = material.get("medblend_preset_data_range")
    try:
        if stored_window is None or len(stored_window) != 2:
            return False
        # Two volumes covering different value ranges need their own Map Range
        # settings, so a material built for one must not be handed to the other.
        if stored_data_range is None or len(stored_data_range) != 2:
            return False
        expected = (
            float(window[0]),
            float(window[1]),
            float(data_range[0]),
            float(data_range[1]),
            float(density_scale),
            float(emission_strength),
        )
        actual = (
            float(stored_window[0]),
            float(stored_window[1]),
            float(stored_data_range[0]),
            float(stored_data_range[1]),
            float(material.get("medblend_preset_density_scale", float("nan"))),
            float(material.get("medblend_preset_emission_strength", float("nan"))),
        )
    except (TypeError, ValueError):
        return False

    return all(
        abs(a - b) <= _FLOAT_TOLERANCE
        for a, b in zip(expected, actual, strict=True)
    )


def _candidate_name(base_name: str, counter: int) -> str:
    suffix = "" if counter == 0 else f"_{counter}"
    return base_name[: _MAX_DATABLOCK_NAME - len(suffix)] + suffix


def get_preset_material(
    preset: VolumePreset,
    window: Sequence[float],
    data_range: Optional[Sequence[float]] = None,
    density_scale: float = DEFAULT_DENSITY_SCALE,
    emission_strength: float = DEFAULT_EMISSION_STRENGTH,
) -> bpy.types.Material:
    """Return the material for these settings, building it only if needed.

    Re-applying the same preset with the same settings hands back the same
    datablock, so a user's edits to it survive and repeated applies do not
    fill the file with copies. Different settings get their own material
    rather than retinting one already in use by another volume.

    ``data_range`` defaults to ``window``, which reads the preset's scalars as
    voxel values directly.
    """

    if data_range is None:
        data_range = window

    base_name = f"{_MATERIAL_PREFIX} - {preset.name}"

    for counter in range(100):
        candidate = _candidate_name(base_name, counter)
        existing = bpy.data.materials.get(candidate)
        if existing is None:
            material = bpy.data.materials.new(candidate)
            break
        if _matches(existing, preset, window, data_range, density_scale, emission_strength):
            return existing
    else:
        material = bpy.data.materials.new(base_name)

    build_preset_node_tree(
        material, preset, window, data_range, density_scale, emission_strength
    )
    _tag_material(material, preset, window, data_range, density_scale, emission_strength)
    material.diffuse_color = _linear_rgba(preset_lib.representative_color(preset))
    return material


def _assign_material(obj: Optional[bpy.types.Object], material: bpy.types.Material) -> bool:
    """Make ``material`` the object's only material.

    Only the first slot is used when rendering a volume, so a preset replaces
    what is there rather than appending a slot that would never be seen.
    """

    slots = getattr(getattr(obj, "data", None), "materials", None)
    if slots is None:
        return False
    slots.clear()
    slots.append(material)
    return True


def volume_intensity_range(obj: bpy.types.Object) -> tuple[Optional[float], Optional[float]]:
    """Read the source intensity range MedBlend recorded on an imported volume."""

    try:
        low = obj.get("medblend_intensity_min")
        high = obj.get("medblend_intensity_max")
        return (None if low is None else float(low), None if high is None else float(high))
    except (TypeError, ValueError):
        return None, None


def apply_volume_preset(
    obj: Optional[bpy.types.Object],
    preset_name: str,
    fit_mode: str = FIT_AUTO,
    density_scale: float = DEFAULT_DENSITY_SCALE,
    emission_strength: float = DEFAULT_EMISSION_STRENGTH,
    on_error: Optional[Callable[[str], None]] = None,
) -> Optional[bpy.types.Material]:
    """Apply the named preset to ``obj``, returning the material used.

    ``on_error`` receives the failure message instead of a popup being shown,
    so an operator can route it through ``self.report``.
    """

    def fail(message: str) -> None:
        if on_error is not None:
            on_error(message)
        else:
            show_message_box(message, "Error", "ERROR")
        return None

    preset = preset_lib.get_preset(preset_name)
    if preset is None:
        return fail(f"Unknown volume preset '{preset_name}'.")

    if obj is None or getattr(obj, "type", None) != "VOLUME":
        return fail("Select an imported image volume before applying a preset.")

    intensity_min, intensity_max = volume_intensity_range(obj)
    window = preset_lib.resolve_window(
        preset,
        intensity_min,
        intensity_max,
        fit_mode=fit_mode,
        modality=str(obj.get("medblend_modality", "") or ""),
    )
    data_range = preset_lib.resolve_data_range(window, intensity_min, intensity_max)

    try:
        material = get_preset_material(
            preset, window, data_range, density_scale, emission_strength
        )
    except Exception as exc:
        return fail(f"Could not build the '{preset.name}' material: {exc}")

    if not _assign_material(obj, material):
        return fail(f"'{getattr(obj, 'name', '?')}' cannot hold a material.")

    return material
