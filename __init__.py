"""MedBlend - DICOM import tools for Blender."""

from __future__ import annotations

from pathlib import Path

import bpy
from bpy_extras.io_utils import ImportHelper


from .ct import load_ct_series
from .dose import load_dose
from .plan import load_proton_plan
from .structure import load_structures


def _get_prefs(context) -> bpy.types.AddonPreferences | None:
    addon = context.preferences.addons.get(__package__)
    return addon.preferences if addon else None


class MEDBLEND_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    vdb_temp_dir: bpy.props.StringProperty(
        name="VDB Temp Directory",
        description=(
            "Directory to store generated VDB files. If empty, Blender's session "
            "temporary directory is used, which is deleted when Blender exits - "
            "volumes in saved .blend files will then lose their data on reload"
        ),
        subtype="DIR_PATH",
        default="",
    )

    def draw(self, _context):
        layout = self.layout
        layout.prop(self, "vdb_temp_dir")


class MEDBLEND_PT_Main(bpy.types.Panel):
    bl_label = "MedBlend"
    bl_idname = "MEDBLEND_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Medical"

    def draw(self, context):
        layout = self.layout
        layout.label(text="Images")
        layout.operator("medblend.load_ct", text="Load DICOM Images", icon="FILEBROWSER")
        layout.label(text="Dose")
        layout.operator("medblend.load_dose", text="Load DICOM Dose", icon="FILEBROWSER")
        layout.label(text="Structures")
        layout.operator("medblend.load_structures", text="Load DICOM Structures", icon="FILEBROWSER")
        layout.label(text="Proton Spots")
        layout.operator("medblend.load_proton", text="Load Proton Plan", icon="FILEBROWSER")
        layout.separator()
        layout.label(text="VDB Temp Directory")
        prefs = _get_prefs(context)
        if prefs:
            row = layout.row(align=True)
            row.prop(prefs, "vdb_temp_dir", text="")
            row.operator("medblend.select_vdb_temp_dir", text="", icon="FILE_FOLDER")
            row.operator("medblend.clear_vdb_temp_dir", text="", icon="X")
        else:
            layout.label(text="Add-on preferences not available")


class MEDBLEND_OT_Select_Vdb_Temp_Dir(bpy.types.Operator):
    bl_idname = "medblend.select_vdb_temp_dir"
    bl_label = "Select VDB Temp Directory"
    bl_description = "Choose directory for temporary VDB files"

    directory: bpy.props.StringProperty(subtype="DIR_PATH")
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    def execute(self, context):
        prefs = _get_prefs(context)
        if not prefs:
            return {"CANCELLED"}
        selected_dir = Path(self.directory) if self.directory else Path(self.filepath)
        if selected_dir.is_file():
            selected_dir = selected_dir.parent
        prefs.vdb_temp_dir = bpy.path.abspath(str(selected_dir))
        return {"FINISHED"}

    def invoke(self, context, _event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class MEDBLEND_OT_Clear_Vdb_Temp_Dir(bpy.types.Operator):
    bl_idname = "medblend.clear_vdb_temp_dir"
    bl_label = "Clear VDB Temp Directory"
    bl_description = "Use Blender temporary directory for VDB files"

    def execute(self, context):
        prefs = _get_prefs(context)
        if not prefs:
            return {"CANCELLED"}
        prefs.vdb_temp_dir = ""
        return {"FINISHED"}


def _run_import(operator, loader) -> set:
    """Validate the file browser selection, then run ``loader`` on it.

    DICOM files frequently have no extension, so ``filter_glob`` stays at ``*``
    and the selection is checked here instead - picking a directory or leaving
    the field blank would otherwise reach pydicom as a confusing read error.
    """

    if not operator.filepath:
        operator.report({"ERROR"}, "No file was selected.")
        return {"CANCELLED"}

    selected = Path(operator.filepath)
    if not selected.is_file():
        operator.report({"ERROR"}, f"'{selected}' is not a file. Select a single DICOM file.")
        return {"CANCELLED"}

    return {"FINISHED"} if loader(selected) else {"CANCELLED"}


class MEDBLEND_OT_Load_Ct(bpy.types.Operator, ImportHelper):
    bl_idname = "medblend.load_ct"
    bl_label = "Load CT"
    bl_description = "Load a CT Dataset"
    bl_options = {"REGISTER", "UNDO"}
    filter_glob: bpy.props.StringProperty(default="*", options={"HIDDEN"})

    def execute(self, _context):
        return _run_import(self, load_ct_series)


class MEDBLEND_OT_Load_Proton(bpy.types.Operator, ImportHelper):
    bl_idname = "medblend.load_proton"
    bl_label = "Load Proton"
    bl_description = "Load Proton Spots and Weights"
    bl_options = {"REGISTER", "UNDO"}
    filter_glob: bpy.props.StringProperty(default="*", options={"HIDDEN"})

    def execute(self, _context):
        return _run_import(self, load_proton_plan)


class MEDBLEND_OT_Load_Dose(bpy.types.Operator, ImportHelper):
    bl_idname = "medblend.load_dose"
    bl_label = "Load Dose"
    bl_description = "Load a DICOM Dose File"
    bl_options = {"REGISTER", "UNDO"}
    filter_glob: bpy.props.StringProperty(default="*", options={"HIDDEN"})

    def execute(self, _context):
        return _run_import(self, load_dose)


class MEDBLEND_OT_Load_Structures(bpy.types.Operator, ImportHelper):
    bl_idname = "medblend.load_structures"
    bl_label = "Load Structures"
    bl_description = "Load a DICOM Structure Set"
    bl_options = {"REGISTER", "UNDO"}
    filter_glob: bpy.props.StringProperty(default="*", options={"HIDDEN"})

    def execute(self, _context):
        return _run_import(self, load_structures)


classes: tuple[type, ...] = (
    MEDBLEND_Preferences,
    MEDBLEND_PT_Main,
    MEDBLEND_OT_Select_Vdb_Temp_Dir,
    MEDBLEND_OT_Clear_Vdb_Temp_Dir,
    MEDBLEND_OT_Load_Ct,
    MEDBLEND_OT_Load_Proton,
    MEDBLEND_OT_Load_Dose,
    MEDBLEND_OT_Load_Structures,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
