"""MedBlend - DICOM import tools for Blender."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import bpy
import bpy.utils.previews
from bpy_extras.io_utils import ImportHelper

from .ct import load_ct_series
from .dose import load_dose
from .plan import load_proton_plan
from .structure import load_structures


bl_info = {
    "name": "MedBlend",
    "author": "Michael Douglass",
    "version": (2, 0, 0),
    "blender": (5, 0, 0),
    "location": "View3D > Sidebar > Medical",
    "description": "Import DICOM images, dose, structures, and proton plans",
    "category": "3D View",
}


addon_keymaps = {}
_icons = None


class SNA_PT_MEDBLEND_70A7C(bpy.types.Panel):
    bl_label = "MedBlend"
    bl_idname = __package__
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Medical"

    def draw(self, _context):
        layout = self.layout
        layout.label(text="Images")
        layout.operator("medblend.load_ct", text="Load DICOM Images", icon="FILEBROWSER")
        layout.label(text="Dose")
        layout.operator("medblend.load_dose", text="Load DICOM Dose", icon="FILEBROWSER")
        layout.label(text="Structures")
        layout.operator("medblend.load_structures", text="Load DICOM Structures", icon="FILEBROWSER")
        layout.label(text="Proton Spots")
        layout.operator("medblend.load_proton", text="Load Proton Plan", icon="FILEBROWSER")


class SNA_OT_Load_Ct_Fc7B9(bpy.types.Operator, ImportHelper):
    bl_idname = "medblend.load_ct"
    bl_label = "Load CT"
    bl_description = "Load a CT Dataset"
    bl_options = {"REGISTER", "UNDO"}
    filter_glob: bpy.props.StringProperty(default="*.dcm", options={"HIDDEN"})

    def execute(self, _context):
        success = load_ct_series(Path(self.filepath))
        return {"FINISHED"} if success else {"CANCELLED"}


class SNA_OT_Load_Proton_1Dbc6(bpy.types.Operator, ImportHelper):
    bl_idname = "medblend.load_proton"
    bl_label = "Load Proton"
    bl_description = "Load Proton Spots and Weights"
    bl_options = {"REGISTER", "UNDO"}
    filter_glob: bpy.props.StringProperty(default="*.dcm", options={"HIDDEN"})

    def execute(self, _context):
        success = load_proton_plan(Path(self.filepath))
        return {"FINISHED"} if success else {"CANCELLED"}


class SNA_OT_Load_Dose_7629F(bpy.types.Operator, ImportHelper):
    bl_idname = "medblend.load_dose"
    bl_label = "Load Dose"
    bl_description = "Load a DICOM Dose File"
    bl_options = {"REGISTER", "UNDO"}
    filter_glob: bpy.props.StringProperty(default="*.dcm", options={"HIDDEN"})

    def execute(self, _context):
        success = load_dose(Path(self.filepath))
        return {"FINISHED"} if success else {"CANCELLED"}


class SNA_OT_Load_Structures_5Ebc9(bpy.types.Operator, ImportHelper):
    bl_idname = "medblend.load_structures"
    bl_label = "Load Structures"
    bl_description = "Load a DICOM Structure Set"
    bl_options = {"REGISTER", "UNDO"}
    filter_glob: bpy.props.StringProperty(default="*.dcm", options={"HIDDEN"})

    def execute(self, _context):
        success = load_structures(Path(self.filepath))
        return {"FINISHED"} if success else {"CANCELLED"}


classes: Iterable[type] = (
    SNA_PT_MEDBLEND_70A7C,
    SNA_OT_Load_Ct_Fc7B9,
    SNA_OT_Load_Proton_1Dbc6,
    SNA_OT_Load_Dose_7629F,
    SNA_OT_Load_Structures_5Ebc9,
)


def register():
    global _icons
    _icons = bpy.utils.previews.new()
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    global _icons
    bpy.utils.previews.remove(_icons)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

