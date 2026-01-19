"""Plan import helpers for proton and photon data."""

from __future__ import annotations

import math
from pathlib import Path

import bpy
import pydicom

from .blender_utils import add_data_fields, create_object
from .node_groups import apply_proton_spots_geo_nodes
from .ui_utils import show_message_box


def is_proton_plan(ds: pydicom.Dataset) -> bool:
    """Return ``True`` when the dataset represents an RT Ion plan."""

    try:
        return str(ds.Modality).upper() == "RTION"
    except Exception:
        return False


def is_photon_plan(ds: pydicom.Dataset) -> bool:
    """Return ``True`` when the dataset represents an RT Photon plan."""

    try:
        return str(ds.Modality).upper() == "RTPLAN"
    except Exception:
        return False


def load_proton_plan(file_path: Path) -> bool:
    try:
        dataset = pydicom.dcmread(file_path)
    except Exception as exc:
        show_message_box(f"Unable to read file: {exc}", "Error", "ERROR")
        return False

    if not is_proton_plan(dataset):
        show_message_box("Selected file is not an RT Ion proton plan.", "Error", "ERROR")
        return False

    for beam_index, beam in enumerate(dataset.IonBeamSequence):
        control_points = beam.IonControlPointSequence
        num_control_points = len(control_points)

        x_vals: list[float] = []
        y_vals: list[float] = []
        energies: list[float] = []
        spot_weights: list[float] = []

        for idx in range(0, num_control_points, 2):
            positions = control_points[idx].ScanSpotPositionMap
            weights = control_points[idx].ScanSpotMetersetWeights
            for pos_index in range(0, len(positions), 2):
                x_vals.append(positions[pos_index] / 1000.0)
                y_vals.append(positions[pos_index + 1] / 1000.0)
                energies.append(float(control_points[idx].NominalBeamEnergy) / 1000.0)
                weight_index = int(pos_index / 2)
                spot_weights.append(weights[weight_index])

        mesh = bpy.data.meshes.new(name=f"proton_spots_{beam_index}")
        data_fields = ["spot_x", "spot_y", "spot_E", "spot_weight"]
        add_data_fields(mesh, data_fields)

        count = len(spot_weights)
        mesh.vertices.add(count)

        for row in range(count):
            mesh.attributes["spot_x"].data[row].value = x_vals[row]
            mesh.attributes["spot_y"].data[row].value = y_vals[row]
            mesh.attributes["spot_E"].data[row].value = energies[row]
            mesh.attributes["spot_weight"].data[row].value = spot_weights[row]
            mesh.vertices[row].co = (0.01 * row, 0.0, 0.0)

        mesh.update()
        mesh.validate()

        if mesh.vertices:
            obj = create_object(mesh, mesh.name)
            gantry_angle = float(control_points[0].GantryAngle) if hasattr(control_points[0], "GantryAngle") else 0.0
            iso_center = tuple(val / 1000.0 for val in control_points[0].IsocenterPosition)
            obj.rotation_euler[1] = gantry_angle * math.pi / 180.0
            obj.location = (iso_center[0], iso_center[1], iso_center[2])
            apply_proton_spots_geo_nodes(node_tree_name="Proton_Spots")

    return True
