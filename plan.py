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


def _spot_control_point_data(
    control_point: pydicom.Dataset,
) -> tuple[list[float], list[float], float]:
    """Validate and return spot positions, weights and nominal energy.

    Malformed values are isolated to their control point so one bad energy
    layer does not abort beams that have already imported or prevent later
    valid layers from being processed.
    """

    try:
        positions = _as_float_list(getattr(control_point, "ScanSpotPositionMap", None))
        weights = _as_float_list(getattr(control_point, "ScanSpotMetersetWeights", None))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("spot positions or weights contain a non-numeric value") from exc

    if not positions or not weights:
        raise ValueError("spot positions or weights are missing")
    if len(positions) % 2 != 0:
        raise ValueError("the spot position map contains an odd number of values")

    spot_count = len(positions) // 2
    if len(weights) != spot_count:
        raise ValueError(
            f"the position map contains {spot_count} spots but {len(weights)} weights"
        )

    declared_count = getattr(control_point, "NumberOfScanSpotPositions", None)
    if declared_count not in (None, ""):
        try:
            declared_count = int(declared_count)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("NumberOfScanSpotPositions is non-numeric") from exc
        if declared_count != spot_count:
            raise ValueError(
                f"NumberOfScanSpotPositions is {declared_count}, but the position map "
                f"contains {spot_count} spots"
            )

    raw_energy = getattr(control_point, "NominalBeamEnergy", None)
    try:
        nominal_energy_mev = float(raw_energy)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("NominalBeamEnergy is missing or non-numeric") from exc

    numeric_values = positions + weights + [nominal_energy_mev]
    if not all(math.isfinite(value) for value in numeric_values):
        raise ValueError("spot positions, weights and energy must all be finite")
    if nominal_energy_mev <= 0:
        raise ValueError("NominalBeamEnergy must be greater than zero")
    if any(weight < 0 for weight in weights):
        raise ValueError("spot meterset weights cannot be negative")

    return positions, weights, nominal_energy_mev / 1000.0


def _patient_position(dataset: pydicom.Dataset) -> str:
    try:
        setups = getattr(dataset, "PatientSetupSequence", [])
        if setups:
            return str(getattr(setups[0], "PatientPosition", "")).upper()
    except Exception:
        pass
    return ""


# The Proton_Spots node group places each spot at the object-local position
# (spot_x, spot_y, spot_E), so the object's local axes are the IEC 61217 beam
# limiting device axes. For a head-first supine patient at gantry and couch
# zero those map into DICOM patient coordinates as:
#
#     X_b (spot_x) -> +X   patient left
#     Y_b (spot_y) -> +Z   patient superior
#     Z_b (spot_E) -> -Y   patient anterior, back towards the source
#
# which is a +90 degree rotation about X. Leaving it out - as an identity base
# frame does - puts the spot plane in the DICOM XY plane, so spot_y runs
# anterior-posterior instead of superior-inferior, and the gantry rotation
# about +Z never moves the beam axis off the patient's long axis at all.
IEC_BEAM_TO_DICOM = Matrix.Rotation(math.radians(90.0), 4, "X")


def _beam_world_matrix(control_point: pydicom.Dataset) -> Matrix:
    """Build the beam object's world matrix in DICOM patient coordinates.

    Assumes a head-first supine (HFS) patient. The IEC gantry rotation axis is
    then the patient superior-inferior axis (DICOM +Z), and the couch
    (PatientSupportAngle) turns the beam about the room-vertical axis, which
    lies along DICOM Y. Composing couch after gantry reproduces the standard
    beam direction of travel ``(-sinG cosT, cosG, sinG sinT)``: gantry 0 enters
    anteriorly and gantry 90 is a left lateral beam.

    ``spot_E`` is stacked along +Z_b, so higher energy layers are drawn further
    back towards the source rather than deeper into the patient. That is the
    existing depiction, kept as-is; the sign of the attribute is what would
    change it, not this matrix.
    """

    gantry_angle = float_or(getattr(control_point, "GantryAngle", None), 0.0)
    couch_angle = float_or(getattr(control_point, "PatientSupportAngle", None), 0.0)
    # IsocenterPosition is Type 1C and may be absent or empty on the first
    # control point, in which case the beam sits at the scene origin.
    iso_center_raw = getattr(control_point, "IsocenterPosition", None) or (0.0, 0.0, 0.0)
    iso_center = tuple(float_or(value, 0.0) / 1000.0 for value in iso_center_raw)
    if len(iso_center) != 3:
        iso_center = (0.0, 0.0, 0.0)

    rotation = (
        Matrix.Rotation(math.radians(couch_angle), 4, "Y")
        @ Matrix.Rotation(math.radians(gantry_angle), 4, "Z")
        @ IEC_BEAM_TO_DICOM
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
            try:
                positions, weights, nominal_energy = _spot_control_point_data(control_point)
            except ValueError as exc:
                warnings.append(
                    f"Beam {beam_index} control point {idx} was skipped: {exc}."
                )
                continue

            spot_count = len(weights)
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
