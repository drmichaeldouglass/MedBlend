"""Operator that imports DICOM dose grids."""

from __future__ import annotations

from pathlib import Path

import bpy
from bpy_extras.io_utils import ImportHelper

from .. import dependencies
from ..messages import show_message
from ..utils import dicom, nodes


class MEDBLEND_OT_load_dose(bpy.types.Operator, ImportHelper):
    """Import a radiotherapy dose grid as an OpenVDB volume."""

    bl_idname = "medblend.load_dose"
    bl_label = "Load DICOM Dose"
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
        if not dicom.is_dose(dataset):
            show_message("Selected file is not a DICOM RT Dose dataset.", icon='ERROR')
            return {'CANCELLED'}

        try:
            dose_matrix = numpy.array(dataset.pixel_array, dtype=float)
        except Exception:
            show_message("Unable to read the dose pixel data from the file.", icon='ERROR')
            return {'CANCELLED'}

        dose_matrix = numpy.flip(dose_matrix, axis=0)

        spacing = _extract_voxel_spacing(dataset)
        grid = openvdb.FloatGrid()
        grid.copyFromArray(dose_matrix)
        grid.transform = openvdb.createLinearTransform([
            [spacing[2], 0.0, 0.0, 0.0],
            [0.0, spacing[0], 0.0, 0.0],
            [0.0, 0.0, spacing[1], 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ])
        grid.gridClass = openvdb.GridClass.FOG_VOLUME
        grid.name = "density"

        output_path = Path(self.filepath).parent / "medblend_dose.vdb"
        openvdb.write(str(output_path), grid)

        bpy.ops.object.volume_import(filepath=str(output_path))
        nodes.apply_material("Dose Material")
        return {'FINISHED'}


def _extract_voxel_spacing(dataset) -> tuple[float, float, float]:
    """Return the voxel spacing in metres for *dataset*."""

    try:
        xy_spacing = [float(v) for v in dataset.PixelSpacing]
    except Exception:
        xy_spacing = [1.0, 1.0]

    try:
        z_spacing = float(dataset.SliceThickness)
    except Exception:
        z_spacing = 1.0

    return (xy_spacing[0] / 1000.0, xy_spacing[1] / 1000.0, z_spacing / 1000.0)


__all__ = ["MEDBLEND_OT_load_dose"]
