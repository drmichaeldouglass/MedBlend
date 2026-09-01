"""Volume rendering presets modelled on 3D Slicer's.

Slicer describes a preset with two piecewise-linear transfer functions keyed
by scalar value - a colour function and a scalar opacity function. MedBlend
normalises every imported image volume to ``0 - 1`` and records the source
range on the object, so a preset is applied by resampling both functions onto
that normalised axis and feeding them into colour ramps in the volume shader.

Everything in this module is plain data and arithmetic; the Blender node tree
is built in :mod:`volume_materials`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from .preset_data import PRESETS as _PRESET_DATA

ColorPoint = Tuple[float, float, float, float]
OpacityPoint = Tuple[float, float]
RampStop = Tuple[float, Tuple[float, ...]]

# Distinct positions that a colour ramp can still resolve as a hard step.
# Slicer's transfer functions repeat a scalar value to express a
# discontinuity, which a Blender colour ramp cannot represent directly.
_MIN_STOP_SEPARATION = 1e-5

#: Identifier used by the UI to mean "leave the default material alone".
NO_PRESET = "NONE"

#: Scalar values of ``CT-`` presets are Hounsfield units, which are calibrated
#: and therefore meaningful without reference to a particular scan.
_ABSOLUTE_PREFIXES = ("CT-",)

#: Modalities whose voxels are in a calibrated absolute unit (Hounsfield).
_ABSOLUTE_MODALITIES = frozenset({"CT"})

FIT_AUTO = "AUTO"
FIT_ABSOLUTE = "ABSOLUTE"
FIT_RANGE = "FIT"

#: Items for the "how should the preset's scalars be interpreted" dropdown.
FIT_MODE_ENUM_ITEMS = (
    (
        FIT_AUTO,
        "Auto",
        "Read CT presets in Hounsfield units on CT volumes, and stretch the "
        "preset's window over the data range for everything else",
    ),
    (
        FIT_ABSOLUTE,
        "Hounsfield Units",
        "Read the preset's scalars as Hounsfield units and map them onto the "
        "volume's recorded intensity range",
    ),
    (
        FIT_RANGE,
        "Fit To Data",
        "Stretch the preset's authored window across the volume's full "
        "intensity range, for data with no calibrated units such as MR",
    ),
)


@dataclass(frozen=True)
class VolumePreset:
    """One Slicer volume property, in Slicer's own units."""

    name: str
    description: str
    color: Tuple[ColorPoint, ...]
    opacity: Tuple[OpacityPoint, ...]
    effective_range: Optional[Tuple[float, float]]
    ambient: float
    diffuse: float
    specular: float
    specular_power: float
    shade: bool

    @property
    def is_absolute(self) -> bool:
        """``True`` when the preset's scalars are Hounsfield units."""

        return self.name.startswith(_ABSOLUTE_PREFIXES)

    @property
    def scalar_range(self) -> Tuple[float, float]:
        """The full scalar domain both transfer functions are defined over."""

        low = min(self.color[0][0], self.opacity[0][0])
        high = max(self.color[-1][0], self.opacity[-1][0])
        return low, high

    @property
    def window(self) -> Tuple[float, float]:
        """The scalar window worth showing - the authored range if there is one."""

        if self.effective_range is not None:
            return self.effective_range
        return self.scalar_range


def _build_presets() -> Tuple[VolumePreset, ...]:
    return tuple(
        VolumePreset(
            name=entry["name"],
            description=entry["description"],
            color=tuple(tuple(float(v) for v in point) for point in entry["color"]),
            opacity=tuple(tuple(float(v) for v in point) for point in entry["opacity"]),
            effective_range=(
                None if entry["effective_range"] is None else tuple(float(v) for v in entry["effective_range"])
            ),
            ambient=float(entry["ambient"]),
            diffuse=float(entry["diffuse"]),
            specular=float(entry["specular"]),
            specular_power=float(entry["specular_power"]),
            shade=bool(entry["shade"]),
        )
        for entry in _PRESET_DATA
    )


VOLUME_PRESETS: Tuple[VolumePreset, ...] = _build_presets()

_PRESETS_BY_NAME = {preset.name: preset for preset in VOLUME_PRESETS}


def get_preset(name: str) -> Optional[VolumePreset]:
    """Look a preset up by its Slicer name."""

    return _PRESETS_BY_NAME.get(name)


def preset_enum_items(include_none: bool = True) -> tuple:
    """Build ``EnumProperty`` items, grouped by modality with separators.

    The tuple is built once at import time and held module-level: Blender
    reads enum item strings by reference, and items generated per draw call
    are a well-known source of corrupted labels.
    """

    items: list = []
    if include_none:
        items.append(
            (
                NO_PRESET,
                "Default Image Material",
                "Use the MedBlend Image Material shipped in the asset library",
            )
        )

    previous_group = None
    for preset in VOLUME_PRESETS:
        group = preset.name.split("-", 1)[0]
        if previous_group is not None and group != previous_group:
            items.append(None)
        previous_group = group
        items.append((preset.name, preset.name, preset.description))

    return tuple(items)


#: Prebuilt items for the preset dropdowns. Blender needs a stable reference.
PRESET_ENUM_ITEMS = preset_enum_items(include_none=False)
IMPORT_PRESET_ENUM_ITEMS = preset_enum_items(include_none=True)


def _values(point: Sequence[float]) -> Tuple[float, ...]:
    return tuple(float(value) for value in point[1:])


def evaluate(points: Sequence[Sequence[float]], scalar: float) -> Tuple[float, ...]:
    """Evaluate a piecewise-linear transfer function at ``scalar``.

    Values outside the control points are held constant, matching how VTK
    extends a piecewise function past its ends. Slicer repeats a scalar to
    express a step, and the later of the repeated points is the value the
    function takes there - so a step reads as a jump up at that scalar rather
    than one just after it.
    """

    if not points:
        raise ValueError("A transfer function needs at least one control point")

    if scalar < points[0][0]:
        return _values(points[0])

    index = 0
    for candidate, point in enumerate(points):
        if point[0] > scalar:
            break
        index = candidate

    point = points[index]
    if index == len(points) - 1 or point[0] == scalar:
        return _values(point)

    following = points[index + 1]
    weight = (scalar - float(point[0])) / (float(following[0]) - float(point[0]))
    return tuple(
        value + (following_value - value) * weight
        for value, following_value in zip(_values(point), _values(following))
    )


def resample(points: Sequence[Sequence[float]], low: float, high: float) -> list[RampStop]:
    """Resample a transfer function onto ``0 - 1`` over ``[low, high]``.

    Clamping the original control points into range would pile several of
    them onto position 0 or 1 and lose the value the function actually takes
    at the boundary, so the ends are evaluated instead and only the control
    points strictly inside the window are carried across.
    """

    if not points:
        raise ValueError("A transfer function needs at least one control point")
    if not high > low:
        raise ValueError(f"Range must be increasing, got [{low}, {high}]")

    span = high - low
    stops: list[RampStop] = [(0.0, evaluate(points, low))]
    for point in points:
        scalar = float(point[0])
        if low < scalar < high:
            stops.append(((scalar - low) / span, _values(point)))
    stops.append((1.0, evaluate(points, high)))

    return _separate_stops(stops)


def _separate_stops(stops: Sequence[RampStop]) -> list[RampStop]:
    """Force strictly increasing positions, keeping steps as sharp as possible."""

    separated: list[RampStop] = []
    for position, values in stops:
        if separated:
            minimum = separated[-1][0] + _MIN_STOP_SEPARATION
            if position < minimum:
                position = min(minimum, 1.0)
                # A ramp cannot hold two stops at 1.0; drop the earlier one so
                # the function's final value is the one that survives.
                if separated[-1][0] >= position:
                    separated.pop()
        separated.append((position, values))
    return separated


def resolve_window(
    preset: VolumePreset,
    intensity_min: Optional[float],
    intensity_max: Optional[float],
    fit_mode: str = FIT_AUTO,
    modality: str = "",
) -> Tuple[float, float]:
    """Choose the scalar window a preset's transfer functions are stretched over.

    ``FIT_ABSOLUTE`` maps the preset straight onto the volume's own intensity
    range, which is what Hounsfield units call for. ``FIT_RANGE`` instead
    stretches the preset's authored window across whatever range the volume
    happens to occupy - the sensible choice for MR, ultrasound and micro-CT,
    where stored intensities carry no calibrated meaning and vary per scan.
    """

    has_intensity_range = (
        intensity_min is not None and intensity_max is not None and intensity_max > intensity_min
    )

    if fit_mode == FIT_AUTO:
        modality_is_absolute = modality.upper() in _ABSOLUTE_MODALITIES if modality else True
        use_absolute = preset.is_absolute and modality_is_absolute
    else:
        use_absolute = fit_mode == FIT_ABSOLUTE

    if use_absolute and has_intensity_range:
        return float(intensity_min), float(intensity_max)

    return preset.window


def representative_color(preset: VolumePreset) -> ColorPoint:
    """The preset's colour where it is most opaque, for viewport display."""

    peak = max(preset.opacity, key=lambda point: point[1])
    red, green, blue = evaluate(preset.color, peak[0])
    return red, green, blue, 1.0


def srgb_to_linear(value: float) -> float:
    """Convert one sRGB display component to scene-linear.

    Slicer's colour transfer functions hold display-referred sRGB values while
    Blender's colour ramps are scene-linear, so the values have to be
    converted or every preset renders washed out.
    """

    if value <= 0.04045:
        return value / 12.92
    return ((value + 0.055) / 1.055) ** 2.4
