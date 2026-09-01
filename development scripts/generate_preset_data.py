"""Regenerate ``preset_data.py`` from 3D Slicer's volume rendering presets.

Slicer stores its volume rendering presets as ``vtkMRMLVolumePropertyNode``
elements in a single XML file. This script parses that file and writes the
transfer functions out as a plain Python data module so the add-on does not
have to ship an XML parser or read a data file at import time.

Usage::

    python "development scripts/generate_preset_data.py"                 # download
    python "development scripts/generate_preset_data.py" path/presets.xml

The upstream file is licensed under the 3D Slicer license (a BSD-style
licence); see ``licenses/Slicer-License.txt`` and ``THIRD_PARTY_NOTICES.md``.
"""

from __future__ import annotations

import sys
import textwrap
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Sequence

PRESETS_URL = (
    "https://raw.githubusercontent.com/Slicer/Slicer/main/"
    "Modules/Loadable/VolumeRendering/Resources/presets.xml"
)

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "preset_data.py"

# Short, human-readable summaries shown in the preset dropdown. Slicer's XML
# only carries the preset name, so these are maintained here by hand and must
# be kept in step with the upstream preset list.
DESCRIPTIONS = {
    "CT-AAA": "Contrast-enhanced abdominal aortic aneurysm",
    "CT-AAA2": "Abdominal aortic aneurysm with brighter vessel emphasis",
    "CT-Bone": "Bone through translucent skin and soft tissue",
    "CT-Bones": "Bone only, rendered plain white",
    "CT-Cardiac": "Contrast-enhanced cardiac chambers and vessels",
    "CT-Cardiac2": "Cardiac anatomy with bone and vessel contrast",
    "CT-Cardiac3": "Cardiac anatomy with muscle and vessel detail",
    "CT-Chest-Contrast-Enhanced": "Contrast-enhanced chest",
    "CT-Chest-Vessels": "Chest vasculature through soft tissue",
    "CT-Coronary-Arteries": "Coronary arteries, unshaded",
    "CT-Coronary-Arteries-2": "Coronary arteries with the heart wall",
    "CT-Coronary-Arteries-3": "Coronary arteries with surrounding tissue",
    "CT-Cropped-Volume-Bone": "Bone, tuned for cropped volumes",
    "CT-Fat": "Subcutaneous and visceral fat",
    "CT-Liver-Vasculature": "Contrast-enhanced liver vasculature",
    "CT-Lung": "Lung parenchyma and airways",
    "CT-MIP": "Greyscale maximum-intensity-projection look",
    "CT-Muscle": "Muscle and soft tissue",
    "CT-Pulmonary-Arteries": "Contrast-enhanced pulmonary arteries",
    "CT-Soft-Tissue": "Soft tissue beneath skin",
    "CT-Air": "Air-filled cavities and airways",
    "CT-X-ray": "Flat white, radiograph-like transmission",
    "MR-Angio": "MR angiography vessels",
    "MR-Default": "General-purpose MR",
    "MR-MIP": "MR maximum-intensity-projection look",
    "MR-T2-Brain": "T2-weighted brain",
    "DTI-FA-Brain": "Fractional anisotropy map (0 - 1 scalar)",
    "US-Fetal": "3D fetal ultrasound",
    "uCT-Bone-8bit": "Micro-CT bone, 8-bit data",
    "uCT-Bone-16bit": "Micro-CT bone, 16-bit data",
    "uCT-Skull": "Micro-CT skull",
}


def parse_points(text: str, stride: int) -> list[tuple[float, ...]]:
    """Parse a VTK piecewise function: a count followed by flat tuples."""

    fields = text.split()
    count = int(fields[0])
    values = [float(field) for field in fields[1:]]
    if count != len(values):
        raise ValueError(f"Declared {count} values but found {len(values)}")
    if len(values) % stride:
        raise ValueError(f"{len(values)} values is not a multiple of {stride}")
    return [tuple(values[i : i + stride]) for i in range(0, len(values), stride)]


def parse_effective_range(text: Optional[str]) -> Optional[tuple[float, float]]:
    """Parse ``effectiveRange``, returning ``None`` when it is unusable.

    Upstream contains malformed (``-250.0.0 1550.0``) and placeholder
    (``0 -1``) values, so anything that does not parse as an increasing pair
    is dropped rather than being carried into the add-on as bad data.
    """

    if not text:
        return None
    fields = text.split()
    if len(fields) != 2:
        return None
    try:
        low, high = float(fields[0]), float(fields[1])
    except ValueError:
        return None
    if not (low < high):
        return None
    return low, high


def quote(text: str) -> str:
    """Double-quoted string literal, matching the add-on's quoting style."""

    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def format_points(points: Sequence[Sequence[float]], indent: str) -> str:
    lines = [f"{indent}(" + ", ".join(repr(value) for value in point) + ")," for point in points]
    return "\n".join(lines)


def build_module(root: ET.Element) -> str:
    entries = []
    dropped: list[str] = []

    for element in root:
        name = element.get("name")
        if not name:
            continue
        color = parse_points(element.get("colorTransfer", "0"), 4)
        opacity = parse_points(element.get("scalarOpacity", "0"), 2)
        effective_range = parse_effective_range(element.get("effectiveRange"))
        if effective_range is None:
            dropped.append(name)

        description = DESCRIPTIONS.get(name, "")
        if not description:
            print(f"warning: no description for preset {name!r}", file=sys.stderr)

        entries.append(
            "    {\n"
            f"        \"name\": {quote(name)},\n"
            f"        \"description\": {quote(description)},\n"
            "        \"color\": (\n"
            f"{format_points(color, ' ' * 12)}\n"
            "        ),\n"
            "        \"opacity\": (\n"
            f"{format_points(opacity, ' ' * 12)}\n"
            "        ),\n"
            f"        \"effective_range\": {effective_range!r},\n"
            f"        \"ambient\": {float(element.get('ambient', 0.0))!r},\n"
            f"        \"diffuse\": {float(element.get('diffuse', 1.0))!r},\n"
            f"        \"specular\": {float(element.get('specular', 0.0))!r},\n"
            f"        \"specular_power\": {float(element.get('specularPower', 1.0))!r},\n"
            f"        \"shade\": {bool(int(element.get('shade', 0)))!r},\n"
            "    },"
        )

    dropped_note = textwrap.fill(
        "Presets with no usable upstream range: "
        + (", ".join(dropped) if dropped else "none")
        + ".",
        width=74,
        break_on_hyphens=False,
        initial_indent="    ",
        subsequent_indent="    ",
    )
    header = f'''"""Volume rendering transfer functions ported from 3D Slicer.

Generated by ``development scripts/generate_preset_data.py`` - do not edit by
hand. The source is Slicer's ``Modules/Loadable/VolumeRendering/Resources/
presets.xml``, which is licensed under the 3D Slicer license (a BSD-style
licence reproduced in ``licenses/Slicer-License.txt``).

All or portions of this licensed product (such portions are the "Software")
have been obtained under license from The Brigham and Women's Hospital, Inc.
and are subject to the terms and conditions in ``licenses/Slicer-License.txt``.

Each entry holds the preset exactly as Slicer defines it:

``color``
    ``(scalar, r, g, b)`` control points of the colour transfer function. The
    scalar is in the source modality's own units - Hounsfield units for the
    ``CT-`` presets, raw stored intensities otherwise. Colours are the sRGB
    display values Slicer uses, not scene-linear values.
``opacity``
    ``(scalar, alpha)`` control points of the scalar opacity function.
``effective_range``
    The scalar window the preset was authored for, or ``None`` when upstream
    has no usable value.

{dropped_note}
``ambient``/``diffuse``/``specular``/``specular_power``/``shade``
    Slicer's Phong shading parameters, kept for reference. Blender's volume
    shader is physically based and has no Phong term, so ``presets.py`` records
    them on the generated material rather than wiring them into the node tree.

Slicer's ``gradientOpacity`` functions are not ported: Blender's shader nodes
cannot read a volume's gradient magnitude, so there is nothing to drive.
"""

from __future__ import annotations

PRESETS = (
'''
    return header + "\n".join(entries) + "\n)\n"


def main(argv: Sequence[str]) -> int:
    if len(argv) > 1:
        source = Path(argv[1]).read_text(encoding="utf-8")
    else:
        print(f"Downloading {PRESETS_URL}")
        with urllib.request.urlopen(PRESETS_URL) as response:
            source = response.read().decode("utf-8")

    root = ET.fromstring(source)
    OUTPUT_PATH.write_text(build_module(root), encoding="utf-8")
    print(f"Wrote {len(list(root))} presets to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
