"""Operator that imports DICOM proton spot maps."""

from __future__ import annotations

import math

import bpy
from bpy_extras.io_utils import ImportHelper

from .. import dependencies
from ..messages import show_message
from ..utils import nodes, proton
from ..utils import blender as blender_utils


class MEDBLEND_OT_load_proton(bpy.types.Operator, ImportHelper):
    """Import proton therapy spot positions and weights."""

    bl_idname = "medblend.load_proton"
    bl_label = "Load Proton Plan"
    bl_options = {"REGISTER", "UNDO"}

    filter_glob: bpy.props.StringProperty(default="*.dcm", options={'HIDDEN'})

    _REQUIRED = ("pydicom",)

    def execute(self, context: bpy.types.Context):
        try:
            modules = dependencies.ensure_dependencies(*self._REQUIRED)
        except dependencies.DependencyError as exc:
            show_message(str(exc), icon='ERROR')
            return {'CANCELLED'}

        pydicom = modules["pydicom"]

        dataset = pydicom.dcmread(self.filepath)
        if not proton.is_proton_plan(dataset):
            show_message("Selected file is not a proton therapy plan.", icon='ERROR')
            return {'CANCELLED'}

        try:
            beams = dataset.IonBeamSequence
        except AttributeError:
            show_message("Plan does not contain an ion beam sequence.", icon='ERROR')
            return {'CANCELLED'}

        for index, beam in enumerate(beams):
            self._create_beam_object(index, beam)

        return {'FINISHED'}

    def _create_beam_object(self, index, beam):
        control_points = getattr(beam, "IonControlPointSequence", None)
        if not control_points:
            return

        spot_positions = []
        spot_weights = []
        spot_energies = []

        for cp_index in range(0, len(control_points), 2):
            control_point = control_points[cp_index]
            position_map = getattr(control_point, "ScanSpotPositionMap", [])
            weights = getattr(control_point, "ScanSpotMetersetWeights", [])
            try:
                energy = float(control_point.NominalBeamEnergy) / 1000.0
            except Exception:
                energy = 0.0

            for pos_index in range(0, len(position_map), 2):
                x = position_map[pos_index] / 1000.0
                y = position_map[pos_index + 1] / 1000.0
                spot_positions.append((x, y))
                spot_weights.append(weights[pos_index // 2] if pos_index // 2 < len(weights) else 0.0)
                spot_energies.append(energy)

        if not spot_positions:
            return

        mesh = bpy.data.meshes.new(name=f"proton_spots_{index}")
        vertex_count = len(spot_positions)
        mesh.vertices.add(vertex_count)

        blender_utils.add_vertex_float_attributes(mesh, ["spot_x", "spot_y", "spot_energy", "spot_weight"])

        for row in range(vertex_count):
            mesh.vertices[row].co = (0.01 * row, 0.0, 0.0)
            mesh.attributes['spot_x'].data[row].value = spot_positions[row][0]
            mesh.attributes['spot_y'].data[row].value = spot_positions[row][1]
            mesh.attributes['spot_energy'].data[row].value = spot_energies[row]
            mesh.attributes['spot_weight'].data[row].value = spot_weights[row]

        mesh.validate()
        mesh.update()

        obj = blender_utils.create_mesh_object(mesh, f"Proton_Spots_{index}")

        gantry_angle = math.radians(float(getattr(control_points[0], "GantryAngle", 0.0)))
        isocenter = getattr(control_points[0], "IsocenterPosition", (0.0, 0.0, 0.0))

        obj.rotation_euler[1] = gantry_angle
        obj.location = (
            isocenter[0] / 1000.0,
            isocenter[1] / 1000.0,
            isocenter[2] / 1000.0,
        )

        nodes.apply_geometry_nodes("Proton_Spots")


__all__ = ["MEDBLEND_OT_load_proton"]
