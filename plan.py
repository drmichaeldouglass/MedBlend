"""Proton (RT Ion) plan import helpers."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Iterable

import bpy
import pydicom
from mathutils import Matrix

from .blender_utils import add_data_fields, create_object
from .dicom_util import float_or
from .node_groups import apply_proton_spots_geo_nodes
from .ui_utils import show_message_box


RT_ION_PLAN_STORAGE_UID = "1.2.840.10008.5.1.4.1.1.481.8"


def is_proton_plan(ds: pydicom.Dataset) -> bool:
    """Return ``True`` when the dataset represents an RT Ion plan.

    Real RT Ion Plan files carry ``Modality`` "RTPLAN" - the RT Series module
    shares its enumerated values with the conventional RT Plan IOD, and the
    ion variant is identified by its SOP Class UID instead. Matching only on a
    literal "RTION" modality rejected every standards-conformant plan, so
    accept the SOP Class UID, and otherwise fall back to an RT plan that
    actually carries an ``IonBeamSequence``.
    """

    try:
        if str(getattr(ds, "SOPClassUID", "")) == RT_ION_PLAN_STORAGE_UID:
            return True
        modality = str(getattr(ds, "Modality", "")).upper().strip()
        if modality == "RTION":
            return True
        if modality == "RTPLAN" and getattr(ds, "IonBeamSequence", None) is not None:
            return True
    except Exception:
        return False
    return False


def _as_float_list(values) -> list[float]:
    if values is None:
        return []
    if isinstance(values, (str, bytes)):
        return []
    if isinstance(values, Iterable):
        return [float(value) for value in values]
    return [float(values)]


def _patient_position(dataset: pydicom.Dataset) -> str:
    try:
        setups = getattr(dataset, "PatientSetupSequence", [])
        if setups:
            return str(getattr(setups[0], "PatientPosition", "")).upper()
    except Exception:
        pass
    return ""


def _beam_world_matrix(control_point: pydicom.Dataset) -> Matrix:
    """Build the beam object's world matrix in DICOM patient coordinates.

    Assumes a head-first supine (HFS) patient: the IEC gantry rotation axis is
    the patient superior-inferior axis (DICOM +Z), and the couch
    (PatientSupportAngle) rotates the beam about the room-vertical axis, which
    maps to the patient +Y axis in this convention.
    """

    gantry_angle = float_or(getattr(control_point, "GantryAngle", None), 0.0)
    couch_angle = float_or(getattr(control_point, "PatientSupportAngle", None), 0.0)
    # IsocenterPosition is Type 1C and may be absent or empty on the first
    # control point, in which case the beam sits at the scene origin.
    iso_center_raw = getattr(control_point, "IsocenterPosition", None) or (0.0, 0.0, 0.0)
    iso_center = tuple(float_or(value, 0.0) / 1000.0 for value in iso_center_raw)
    if len(iso_center) != 3:
        iso_center = (0.0, 0.0, 0.0)

    rotation = Matrix.Rotation(math.radians(couch_angle), 4, "Y") @ Matrix.Rotation(
        math.radians(gantry_angle), 4, "Z"
    )
    return Matrix.Translation(iso_center) @ rotation


def load_proton_plan(file_path: Path) -> bool:
    try:
        dataset = pydicom.dcmread(file_path)
    except Exception as exc:
        show_message_box(f"Unable to read file: {exc}", "Error", "ERROR")
        return False

    if not is_proton_plan(dataset):
        show_message_box("Selected file is not an RT Ion proton plan.", "Error", "ERROR")
        return False

    ion_beams = getattr(dataset, "IonBeamSequence", None)
    if not ion_beams:
        show_message_box("RT Ion plan is missing IonBeamSequence.", "Error", "ERROR")
        return False

    warnings: list[str] = []
    patient_position = _patient_position(dataset)
    if patient_position and patient_position != "HFS":
        warnings.append(
            f"Patient position is {patient_position}; beam orientation assumes HFS."
        )

    imported_beam_count = 0

    for beam_index, beam in enumerate(ion_beams):
        control_points = getattr(beam, "IonControlPointSequence", None)
        if not control_points:
            warnings.append(f"Beam {beam_index} has no control points.")
            continue

        num_control_points = len(control_points)

        x_vals: list[float] = []
        y_vals: list[float] = []
        energies: list[float] = []
        spot_weights: list[float] = []

        # Spot data lives on the first control point of each pair; the second
        # of a pair only carries cumulative meterset bookkeeping.
        for idx in range(0, num_control_points, 2):
            control_point = control_points[idx]
            positions = _as_float_list(getattr(control_point, "ScanSpotPositionMap", None))
            weights = _as_float_list(getattr(control_point, "ScanSpotMetersetWeights", None))
            if not positions or not weights:
                warnings.append(
                    f"Beam {beam_index} control point {idx} is missing spot positions or weights."
                )
                continue
            if len(positions) % 2 != 0:
                warnings.append(
                    f"Beam {beam_index} control point {idx} has an odd number of spot positions."
                )
                continue

            spot_count = len(positions) // 2
            if len(weights) < spot_count:
                warnings.append(
                    f"Beam {beam_index} control point {idx} has fewer weights than positions."
                )
                continue

            nominal_energy = float(getattr(control_point, "NominalBeamEnergy", 0.0) or 0.0) / 1000.0
            for spot_index in range(spot_count):
                pos_index = spot_index * 2
                x_vals.append(positions[pos_index] / 1000.0)
                y_vals.append(positions[pos_index + 1] / 1000.0)
                energies.append(nominal_energy)
                spot_weights.append(weights[spot_index])

        count = len(spot_weights)
        if count == 0:
            warnings.append(f"Beam {beam_index} did not contain any valid scan spot data.")
            continue

        mesh = bpy.data.meshes.new(name=f"proton_spots_{beam_index}")
        # Add the vertices before the attribute layers so each layer is created
        # already sized to the point domain.
        mesh.vertices.add(count)
        add_data_fields(mesh, ["spot_x", "spot_y", "spot_E", "spot_weight"])

        mesh.attributes["spot_x"].data.foreach_set("value", x_vals)
        mesh.attributes["spot_y"].data.foreach_set("value", y_vals)
        mesh.attributes["spot_E"].data.foreach_set("value", energies)
        mesh.attributes["spot_weight"].data.foreach_set("value", spot_weights)
        coords = [0.0] * (count * 3)
        coords[::3] = [0.01 * row for row in range(count)]
        mesh.vertices.foreach_set("co", coords)

        mesh.validate()
        mesh.update()

        if mesh.vertices:
            obj = create_object(mesh, mesh.name)
            obj.matrix_world = _beam_world_matrix(control_points[0])
            obj["medblend_beam_number"] = int(float_or(getattr(beam, "BeamNumber", beam_index), beam_index))
            beam_name = str(getattr(beam, "BeamName", "") or "")
            if beam_name:
                obj["medblend_beam_name"] = beam_name
            apply_proton_spots_geo_nodes(node_tree_name="Proton_Spots", obj=obj)
            imported_beam_count += 1
        else:
            bpy.data.meshes.remove(mesh)

    if imported_beam_count == 0:
        show_message_box(
            "No proton beam spot data could be imported from this RT Ion plan.",
            "Error",
            "ERROR",
        )
        return False

    if warnings:
        preview = "; ".join(warnings[:3])
        if len(warnings) > 3:
            preview += f"; and {len(warnings) - 3} more"
        show_message_box(
            f"Imported {imported_beam_count} beam(s) with {len(warnings)} warning(s): {preview}",
            "Proton Import Warnings",
            "INFO",
        )

    return True
