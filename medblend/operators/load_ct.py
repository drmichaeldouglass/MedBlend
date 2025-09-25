"""Operator that loads CT/MR DICOM series into Blender."""

from __future__ import annotations

from pathlib import Path

import bpy
from bpy_extras.io_utils import ImportHelper

from .. import dependencies
from ..messages import show_message
from ..utils import dicom, nodes


class MEDBLEND_OT_load_ct(bpy.types.Operator, ImportHelper):
    """Import a CT or MR image stack as an OpenVDB volume."""

    bl_idname = "medblend.load_ct"
    bl_label = "Load DICOM Images"
    bl_options = {"REGISTER", "UNDO"}

    filter_glob: bpy.props.StringProperty(default="*.dcm", options={'HIDDEN'})

    _REQUIRED = ("pydicom", "numpy", "pyopenvdb")

    def execute(self, context: bpy.types.Context):
        try:
            modules = dependencies.ensure_dependencies(*self._REQUIRED)
        except dependencies.DependencyError as exc:
            show_message(str(exc), icon='ERROR')
            return {'CANCELLED'}

        pydicom = modules["pydicom"]
        numpy = modules["numpy"]
        openvdb = modules["pyopenvdb"]

        dataset = pydicom.dcmread(self.filepath)
        if not dicom.is_image(dataset):
            show_message("Selected file is not a CT or MR DICOM image.", icon='ERROR')
            return {'CANCELLED'}

        series_uid = getattr(dataset, "SeriesInstanceUID", None)
        directory = Path(self.filepath).parent
        images = dicom.load_image_series(directory, pydicom=pydicom, series_uid=series_uid)
        volume = dicom.build_volume(images, numpy=numpy)
        if volume is None:
            show_message("Unable to construct a volume from the selected DICOM series.", icon='ERROR')
            return {'CANCELLED'}

        slice_thickness = volume.slice_thickness or 1.0
        pixel_spacing = volume.pixel_spacing or (1.0, 1.0)

        grid = openvdb.FloatGrid()
        grid.copyFromArray(volume.array.astype(float))
        grid.transform = openvdb.createLinearTransform([
            [slice_thickness / 1000.0, 0.0, 0.0, 0.0],
            [0.0, pixel_spacing[0] / 1000.0, 0.0, 0.0],
            [0.0, 0.0, pixel_spacing[1] / 1000.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ])
        grid.gridClass = openvdb.GridClass.FOG_VOLUME
        grid.name = "density"

        output_path = directory / "medblend_ct.vdb"
        openvdb.write(str(output_path), grid)

        bpy.ops.object.volume_import(filepath=str(output_path))
        volume_object = bpy.context.active_object
        if volume_object is not None:
            origin = volume.origin
            if len(origin) >= 3:
                volume_object.location = (
                    origin[2] / 1000.0,
                    origin[1] / 1000.0,
                    origin[0] / 1000.0,
                )

        nodes.apply_material("Image Material")
        return {'FINISHED'}


__all__ = ["MEDBLEND_OT_load_ct"]
