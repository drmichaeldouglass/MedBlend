"""User interface elements for MedBlend."""

from __future__ import annotations

import bpy

from .. import dependencies


class MEDBLEND_PT_panel(bpy.types.Panel):
    bl_label = "MedBlend"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Medical'

    _SECTION_REQUIREMENTS = {
        "medblend.load_ct": ("pydicom", "numpy", "pyopenvdb"),
        "medblend.load_dose": ("pydicom", "numpy", "pyopenvdb"),
        "medblend.load_structures": ("pydicom", "platipy", "SimpleITK", "pyopenvdb"),
        "medblend.load_proton": ("pydicom",),
    }

    _SECTION_ICONS = {
        "medblend.load_ct": 'IMAGE_DATA',
        "medblend.load_dose": 'SHADING_RENDERED',
        "medblend.load_structures": 'MOD_BOOLEAN',
        "medblend.load_proton": 'FORCE_HARMONIC',
    }

    def draw(self, context: bpy.types.Context):
        layout = self.layout
        self._draw_section(layout, "Images", "medblend.load_ct")
        self._draw_section(layout, "Dose", "medblend.load_dose")
        self._draw_section(layout, "Structures", "medblend.load_structures")
        self._draw_section(layout, "Proton Spots", "medblend.load_proton")

    def _draw_section(self, layout: bpy.types.UILayout, label: str, operator_id: str) -> None:
        layout.label(text=label)
        row = layout.row()
        icon = self._SECTION_ICONS.get(operator_id, 'FILE')
        missing = dependencies.find_missing(self._SECTION_REQUIREMENTS[operator_id])
        row.enabled = not missing
        row.operator(operator_id, text="Load", icon=icon)
        if missing:
            layout.label(text="Missing: " + ", ".join(missing), icon='ERROR')


__all__ = ["MEDBLEND_PT_panel"]
