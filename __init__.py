"""MedBlend - DICOM import tools for Blender.

This module deliberately does not use ``from __future__ import annotations``:
Blender registers ``bpy.props`` declarations by reading a class's
``__annotations__``, and silently ignores any entry that is not a property
object. Deferred (PEP 563) annotations are plain strings, so every property in
this file would be dropped at registration.
"""

from pathlib import Path
from typing import Optional

import bpy
from bpy_extras.io_utils import ImportHelper


from . import presets
from .ct import load_ct_series
from .dose import load_dose
from .plan import load_proton_plan
from .structure import load_structures
from .volume_materials import (
    DEFAULT_DENSITY_SCALE,
    DEFAULT_EMISSION_STRENGTH,
    apply_volume_preset,
)


def _get_prefs(context) -> Optional[bpy.types.AddonPreferences]:
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


def _preset_enum(include_none: bool):
    """Preset dropdown, optionally offering "leave the default material"."""

    return bpy.props.EnumProperty(
        name="Preset",
        description="Volume rendering preset to build the material from",
        items=presets.IMPORT_PRESET_ENUM_ITEMS if include_none else presets.PRESET_ENUM_ITEMS,
        default=presets.NO_PRESET if include_none else presets.VOLUME_PRESETS[0].name,
    )


def _fit_mode_enum():
    return bpy.props.EnumProperty(
        name="Scalar Range",
        description="How the preset's scalar values map onto the imported volume",
        items=presets.FIT_MODE_ENUM_ITEMS,
        default=presets.FIT_AUTO,
    )


def _density_scale_prop():
    return bpy.props.FloatProperty(
        name="Density",
        description=(
            "Extinction of a fully opaque voxel, in 1/m. Raise it for a more solid "
            "volume, lower it to see further inside"
        ),
        default=DEFAULT_DENSITY_SCALE,
        min=0.0,
        soft_max=2000.0,
    )


def _emission_strength_prop():
    return bpy.props.FloatProperty(
        name="Emission",
        description=(
            "Brightness of the volume's own light. Lower it towards zero to light "
            "the volume with scene lights instead"
        ),
        default=DEFAULT_EMISSION_STRENGTH,
        min=0.0,
        soft_max=10.0,
    )


class MEDBLEND_VolumePresetSettings(bpy.types.PropertyGroup):
    """Preset settings shown in the sidebar, stored per scene."""

    preset: _preset_enum(include_none=False)
    fit_mode: _fit_mode_enum()
    density_scale: _density_scale_prop()
    emission_strength: _emission_strength_prop()


def _target_volumes(context) -> list:
    """The volume objects a preset should be applied to.

    Selected volumes are preferred so a preset can be pushed onto several at
    once, falling back to the active object when nothing is selected.
    """

    selected = [
        obj for obj in getattr(context, "selected_objects", []) or [] if obj.type == "VOLUME"
    ]
    if selected:
        return selected
    active = getattr(context, "active_object", None)
    return [active] if active is not None and active.type == "VOLUME" else []


class MEDBLEND_OT_Apply_Volume_Preset(bpy.types.Operator):
    bl_idname = "medblend.apply_volume_preset"
    bl_label = "Apply Preset"
    bl_description = "Build a volume material from the selected preset and assign it"
    bl_options = {"REGISTER", "UNDO"}

    preset: _preset_enum(include_none=False)
    fit_mode: _fit_mode_enum()
    density_scale: _density_scale_prop()
    emission_strength: _emission_strength_prop()

    @classmethod
    def poll(cls, context):
        return bool(_target_volumes(context))

    def execute(self, context):
        volumes = _target_volumes(context)
        if not volumes:
            self.report({"ERROR"}, "Select an imported image volume first.")
            return {"CANCELLED"}

        errors = []
        applied = 0
        for obj in volumes:
            material = apply_volume_preset(
                obj,
                self.preset,
                fit_mode=self.fit_mode,
                density_scale=self.density_scale,
                emission_strength=self.emission_strength,
                on_error=errors.append,
            )
            if material is not None:
                applied += 1

        if not applied:
            self.report({"ERROR"}, errors[0] if errors else "No preset could be applied.")
            return {"CANCELLED"}

        if errors:
            self.report({"WARNING"}, f"{errors[0]} ({len(errors)} volume(s) skipped)")
        self.report({"INFO"}, f"Applied '{self.preset}' to {applied} volume(s).")
        return {"FINISHED"}


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
        layout.label(text="Image Volume Presets")
        settings = getattr(context.scene, "medblend_volume_preset", None)
        if settings is not None:
            layout.prop(settings, "preset", text="")
            layout.prop(settings, "fit_mode", text="")
            layout.prop(settings, "density_scale")
            layout.prop(settings, "emission_strength")
            operator = layout.operator(
                "medblend.apply_volume_preset", text="Apply Preset", icon="MATERIAL"
            )
            operator.preset = settings.preset
            operator.fit_mode = settings.fit_mode
            operator.density_scale = settings.density_scale
            operator.emission_strength = settings.emission_strength
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

    preset: _preset_enum(include_none=True)
    fit_mode: _fit_mode_enum()
    density_scale: _density_scale_prop()
    emission_strength: _emission_strength_prop()

    def execute(self, _context):
        def loader(path):
            return load_ct_series(
                path,
                preset_name=self.preset,
                fit_mode=self.fit_mode,
                density_scale=self.density_scale,
                emission_strength=self.emission_strength,
            )

        return _run_import(self, loader)


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
    MEDBLEND_VolumePresetSettings,
    MEDBLEND_PT_Main,
    MEDBLEND_OT_Apply_Volume_Preset,
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

    bpy.types.Scene.medblend_volume_preset = bpy.props.PointerProperty(
        type=MEDBLEND_VolumePresetSettings
    )


def unregister():
    if hasattr(bpy.types.Scene, "medblend_volume_preset"):
        del bpy.types.Scene.medblend_volume_preset

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
