"""Operator that imports DICOM RT structure sets."""

from __future__ import annotations

import importlib
from pathlib import Path

import bpy
from bpy_extras.io_utils import ImportHelper

from .. import dependencies
from ..messages import show_message
from ..utils import nodes


class MEDBLEND_OT_load_structures(bpy.types.Operator, ImportHelper):
    """Convert contour structures to OpenVDB volumes."""

    bl_idname = "medblend.load_structures"
    bl_label = "Load DICOM Structures"
    bl_options = {"REGISTER", "UNDO"}

    filter_glob: bpy.props.StringProperty(default="*.dcm", options={'HIDDEN'})

    _REQUIRED = ("pydicom", "platipy", "SimpleITK", "pyopenvdb")

    def execute(self, context: bpy.types.Context):
        try:
            modules = dependencies.ensure_dependencies(*self._REQUIRED)
        except dependencies.DependencyError as exc:
            show_message(str(exc), icon='ERROR')
            return {'CANCELLED'}

        pydicom = modules["pydicom"]
        openvdb = modules["pyopenvdb"]
        simpleitk = modules["SimpleITK"]

        directory = Path(self.filepath).parent
        dicom_structure = pydicom.dcmread(self.filepath)

        rtstruct_module = importlib.import_module("platipy.dicom.io.rtstruct_to_nifti")
        try:
            dicom_image = rtstruct_module.read_dicom_image(str(directory))
        except Exception:
            show_message("Unable to read the referenced DICOM image series.", icon='ERROR')
            return {'CANCELLED'}

        try:
            struct_masks, struct_names = rtstruct_module.transform_point_set_from_dicom_struct(dicom_image, dicom_structure)
        except Exception:
            show_message("Failed to convert the structure set into volumetric masks.", icon='ERROR')
            return {'CANCELLED'}

        spacing = dicom_image.GetSpacing()
        node_created = False

        for mask, name in zip(struct_masks, struct_names):
            array = simpleitk.GetArrayFromImage(mask)
            if not array.any():
                continue

            grid = openvdb.FloatGrid()
            grid.copyFromArray(array.astype(float))
            grid.transform = openvdb.createLinearTransform([
                [spacing[2] / 1000.0, 0.0, 0.0, 0.0],
                [0.0, spacing[0] / 1000.0, 0.0, 0.0],
                [0.0, 0.0, spacing[1] / 1000.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ])
            grid.gridClass = openvdb.GridClass.FOG_VOLUME
            grid.name = "density"

            safe_name = _safe_filename(name)
            output_path = directory / f"{safe_name}.vdb"
            openvdb.write(str(output_path), grid)

            bpy.ops.object.volume_import(filepath=str(output_path))
            nodes.apply_material("Structure Material")
            node_created = True

        if not node_created:
            show_message("No valid structures were found in the selected file.", icon='INFO')
            return {'CANCELLED'}

        return {'FINISHED'}


def _safe_filename(name: str) -> str:
    cleaned = name.strip() or "structure"
    allowed = [c if c.isalnum() or c in "-_" else "_" for c in cleaned]
    return "".join(allowed)


__all__ = ["MEDBLEND_OT_load_structures"]
