"""Proton (RT Ion) plan import helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import bpy
import pydicom
from mathutils import Matrix

from .blender_utils import add_data_fields, create_object
from .node_groups import apply_proton_spots_geo_nodes
from .ui_utils import show_message_box


RT_ION_PLAN_STORAGE_UID = "1.2.840.10008.5.1.4.1.1.481.8"


@dataclass(frozen=True)
class _BeamGeometry:
    """Patient-space geometry inherited at one ion control point."""

    gantry_angle: float = 0.0
    couch_angle: float = 0.0
    isocenter_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass
class _SpotGroup:
    """Spots that share one patient-space beam transform."""

    geometry: _BeamGeometry
    x_vals: list[float] = field(default_factory=list)
    y_vals: list[float] = field(default_factory=list)
    energies: list[float] = field(default_factory=list)
    weights: list[float] = field(default_factory=list)
    control_point_indices: list[int] = field(default_factory=list)


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


def _radiation_type(beam: pydicom.Dataset) -> str:
    """Return the normalised DICOM Radiation Type for an ion beam."""

    return str(getattr(beam, "RadiationType", "") or "").strip().upper()


def _finite_float(value, attribute_name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{attribute_name} is non-numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{attribute_name} must be finite")
    return result


def _control_point_geometry(
    control_point: pydicom.Dataset,
    previous: _BeamGeometry | None = None,
) -> _BeamGeometry:
    """Resolve geometry at a control point, inheriting omitted attributes.

    DICOM permits attributes that remain constant for the whole beam to be
    present only at the first control point. Treating an omitted gantry,
    patient-support angle, or isocentre as zero on every later energy layer
    rotates or translates otherwise valid spot maps away from the patient.
    """

    if previous is None:
        previous = _BeamGeometry()

    raw_gantry = getattr(control_point, "GantryAngle", None)
    gantry_angle = (
        previous.gantry_angle
        if raw_gantry in (None, "")
        else _finite_float(raw_gantry, "GantryAngle")
    )

    raw_couch = getattr(control_point, "PatientSupportAngle", None)
    couch_angle = (
        previous.couch_angle
        if raw_couch in (None, "")
        else _finite_float(raw_couch, "PatientSupportAngle")
    )

    raw_isocenter = getattr(control_point, "IsocenterPosition", None)
    if raw_isocenter is None:
        isocenter_mm = previous.isocenter_mm
    else:
        try:
            value_count = len(raw_isocenter)
        except TypeError as exc:
            raise ValueError("IsocenterPosition must contain three values") from exc
        if value_count == 0:
            isocenter_mm = previous.isocenter_mm
        elif value_count != 3:
            raise ValueError("IsocenterPosition must contain three values")
        else:
            isocenter_mm = tuple(
                _finite_float(value, "IsocenterPosition") for value in raw_isocenter
            )

    return _BeamGeometry(gantry_angle, couch_angle, isocenter_mm)


def _collect_spot_groups(
    control_points: Iterable[pydicom.Dataset],
) -> tuple[list[_SpotGroup], list[str]]:
    """Collect irradiation-segment spot maps by their patient transform.

    Every DICOM ion irradiation segment is a pair of control points. The
    first item carries the delivered spot weights. Separate transforms are
    retained for stepped or dynamic arc plans instead of placing the entire
    beam at the geometry of control point zero.
    """

    control_points = list(control_points)
    warnings: list[str] = []
    resolved_geometry: list[_BeamGeometry | None] = []
    current_geometry = _BeamGeometry()

    for index, control_point in enumerate(control_points):
        try:
            current_geometry = _control_point_geometry(control_point, current_geometry)
            resolved_geometry.append(current_geometry)
        except ValueError as exc:
            resolved_geometry.append(None)
            warnings.append(f"control point {index} has invalid geometry: {exc}")

    if len(control_points) % 2:
        warnings.append(
            "the IonControlPointSequence has an odd number of control points; "
            "the final unpaired control point was interpreted as a segment start"
        )

    groups_by_geometry: dict[_BeamGeometry, _SpotGroup] = {}
    for index in range(0, len(control_points), 2):
        geometry = resolved_geometry[index]
        if geometry is None:
            continue

        control_point = control_points[index]
        try:
            positions, weights, nominal_energy = _spot_control_point_data(control_point)
        except ValueError as exc:
            warnings.append(f"control point {index} was skipped: {exc}")
            continue

        end_index = index + 1
        if end_index < len(control_points):
            end_geometry = resolved_geometry[end_index]
            if end_geometry is not None and end_geometry != geometry:
                warnings.append(
                    f"control point pair {index}-{end_index} changes gantry, couch, or "
                    "isocentre during irradiation; its spots are shown at the segment's "
                    "starting geometry"
                )

        group = groups_by_geometry.setdefault(geometry, _SpotGroup(geometry))
        group.control_point_indices.append(index)
        for spot_index, weight in enumerate(weights):
            position_index = spot_index * 2
            group.x_vals.append(positions[position_index] / 1000.0)
            group.y_vals.append(positions[position_index + 1] / 1000.0)
            group.energies.append(nominal_energy)
            group.weights.append(weight)

    return list(groups_by_geometry.values()), warnings


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


def _beam_world_matrix_from_geometry(geometry: _BeamGeometry) -> Matrix:
    """Build a beam transform from already-resolved DICOM geometry."""

    rotation = (
        Matrix.Rotation(math.radians(geometry.couch_angle), 4, "Y")
        @ Matrix.Rotation(math.radians(geometry.gantry_angle), 4, "Z")
        @ IEC_BEAM_TO_DICOM
    )
    translation = tuple(value / 1000.0 for value in geometry.isocenter_mm)
    return Matrix.Translation(translation) @ rotation


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

    return _beam_world_matrix_from_geometry(_control_point_geometry(control_point))


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
    imported_object_count = 0

    for beam_index, beam in enumerate(ion_beams):
        radiation_type = _radiation_type(beam)
        if radiation_type and radiation_type != "PROTON":
            warnings.append(
                f"Beam {beam_index} uses RadiationType {radiation_type} and was skipped; "
                "MedBlend's spot visualisation is proton-specific."
            )
            continue
        if not radiation_type:
            warnings.append(
                f"Beam {beam_index} is missing RadiationType; it was treated as PROTON."
            )

        control_points = getattr(beam, "IonControlPointSequence", None)
        if not control_points:
            warnings.append(f"Beam {beam_index} has no control points.")
            continue

        spot_groups, beam_warnings = _collect_spot_groups(control_points)
        warnings.extend(f"Beam {beam_index} {message}." for message in beam_warnings)
        if not spot_groups:
            warnings.append(f"Beam {beam_index} did not contain any valid scan spot data.")
            continue

        beam_name = str(getattr(beam, "BeamName", "") or "")
        try:
            beam_number = int(getattr(beam, "BeamNumber", beam_index))
        except (TypeError, ValueError, OverflowError):
            beam_number = beam_index
            warnings.append(
                f"Beam {beam_index} has an invalid BeamNumber; index {beam_index} was used."
            )
        imported_group_count = 0
        for group_index, group in enumerate(spot_groups):
            count = len(group.weights)
            suffix = "" if len(spot_groups) == 1 else f"_{group_index}"
            mesh = bpy.data.meshes.new(name=f"proton_spots_{beam_index}{suffix}")
            # Add the vertices before the attribute layers so each layer is
            # created already sized to the point domain.
            mesh.vertices.add(count)
            add_data_fields(mesh, ["spot_x", "spot_y", "spot_E", "spot_weight"])

            mesh.attributes["spot_x"].data.foreach_set("value", group.x_vals)
            mesh.attributes["spot_y"].data.foreach_set("value", group.y_vals)
            mesh.attributes["spot_E"].data.foreach_set("value", group.energies)
            mesh.attributes["spot_weight"].data.foreach_set("value", group.weights)
            coords = [0.0] * (count * 3)
            coords[::3] = [0.01 * row for row in range(count)]
            mesh.vertices.foreach_set("co", coords)

            mesh.validate()
            mesh.update()

            if not mesh.vertices:
                bpy.data.meshes.remove(mesh)
                continue

            obj = create_object(mesh, mesh.name)
            obj.matrix_world = _beam_world_matrix_from_geometry(group.geometry)
            obj["medblend_beam_number"] = beam_number
            obj["medblend_control_point_indices"] = group.control_point_indices
            if beam_name:
                obj["medblend_beam_name"] = beam_name
            apply_proton_spots_geo_nodes(node_tree_name="Proton_Spots", obj=obj)
            imported_group_count += 1
            imported_object_count += 1

        if imported_group_count:
            imported_beam_count += 1

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
            f"Imported {imported_beam_count} beam(s) as {imported_object_count} object(s) "
            f"with {len(warnings)} warning(s): {preview}",
            "Proton Import Warnings",
            "INFO",
        )

    return True
