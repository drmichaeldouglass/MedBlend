"""Conventional RT Plan apertures, expressed in IEC beam coordinates."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import bpy
import pydicom
from mathutils import Matrix

from .plan import IEC_BEAM_TO_DICOM, _finite_float
from .ui_utils import show_message_box
from .volume_utils import ct_patient_to_world, find_ct_anchor


# For HFS the beam basis at zero angles is (left, superior, anterior).
# Other axial setups rotate that room basis about the patient isocentre.
_SETUP_ROLL = {"S": 0, "P": 180, "DL": -90, "DR": 90}
_ANGLES = (
    ("GantryAngle", "GantryRotationDirection", "CW"),
    ("BeamLimitingDeviceAngle", "BeamLimitingDeviceRotationDirection", "CC"),
    ("PatientSupportAngle", "PatientSupportRotationDirection", "CC"),
)
_DEVICE_AXES = {"MLCX": 0, "MLCY": 1, "X": 0, "Y": 1, "ASYMX": 0, "ASYMY": 1}


@dataclass(frozen=True)
class Device:
    kind: str
    pairs: int
    boundaries: tuple[float, ...]
    # Metres at the display plane per projected millimetre at isocentre.
    scale: float
    # Metres from isocentre towards the source.
    height: float


@dataclass(frozen=True)
class ControlPoint:
    isocentre: tuple[float, ...]
    angles: tuple[float, ...]
    tips: dict[str, tuple[float, ...]]


def _values(raw, count, name):
    if (
        raw is None
        or isinstance(raw, (str, bytes))
        or not hasattr(raw, "__len__")
        or len(raw) != count
    ):
        raise ValueError(f"{name} must have {count} values")
    return tuple(_finite_float(value, name) for value in raw)


def _devices(beam, warnings):
    devices = {}
    sad = getattr(beam, "SourceAxisDistance", None)
    if sad is not None:
        sad = _finite_float(sad, "SourceAxisDistance")
        if sad <= 0:
            raise ValueError("SourceAxisDistance must be positive")
    for item in getattr(beam, "BeamLimitingDeviceSequence", []):
        kind = str(getattr(item, "RTBeamLimitingDeviceType", ""))
        if kind not in _DEVICE_AXES or kind in devices:
            raise ValueError(f"unsupported or duplicate beam limiting device {kind!r}")
        pairs = int(getattr(item, "NumberOfLeafJawPairs", 0))
        if pairs < 1 or (not kind.startswith("MLC") and pairs != 1):
            raise ValueError(f"invalid number of {kind} leaf/jaw pairs")
        boundaries = ()
        if kind.startswith("MLC"):
            boundaries = _values(
                getattr(item, "LeafPositionBoundaries", None),
                pairs + 1,
                kind + " boundaries",
            )
            if any(
                end <= start
                for start, end in zip(boundaries, boundaries[1:], strict=False)
            ):
                raise ValueError(f"{kind} boundaries must increase")
        distance = getattr(item, "SourceToBeamLimitingDeviceDistance", None)
        if sad is None:
            scale, height = 0.001, 0.0
            warnings.append(f"{kind} displayed at isocentre (no source-axis distance)")
        else:
            if distance is None:
                # Distinct schematic planes keep the jaws and MLCs visible.
                fraction = {"MLCX": 0.5, "MLCY": 0.52}.get(
                    kind, 0.4 + 0.03 * _DEVICE_AXES[kind]
                )
                distance = sad * fraction
                warnings.append(
                    f"{kind} displayed at an assumed source distance of {distance:g} mm"
                )
            distance = _finite_float(distance, "SourceToBeamLimitingDeviceDistance")
            if not 0 < distance <= sad:
                raise ValueError(f"{kind} source-to-device distance outside (0, SAD]")
            scale, height = distance / sad / 1000, (sad - distance) / 1000
        devices[kind] = Device(kind, pairs, boundaries, scale, height)
    if not devices:
        raise ValueError("no conventional MLC or jaw definitions")
    return devices


def _advance_angle(previous, target, direction, increasing):
    """DICOM direction belongs to the segment starting at the previous CP."""
    coincident = math.isclose(math.remainder(target - previous, 360), 0, abs_tol=1e-8)
    if direction == "NONE":
        if not coincident:
            raise ValueError("angle changes with rotation direction NONE")
        return previous
    if direction not in ("CW", "CC"):
        raise ValueError("missing or invalid rotation direction")
    sign = 1 if direction == increasing else -1
    delta = (sign * (target - previous)) % 360
    # Coincident endpoints with a prescribed rotation describe a full turn.
    return previous + sign * (360 if coincident else delta)


def _control_points(beam, devices):
    points = []
    tips = {}
    directions = [None] * len(_ANGLES)
    iso = None
    table_positions = {}
    for index, cp in enumerate(getattr(beam, "ControlPointSequence", [])):
        if int(getattr(cp, "ControlPointIndex", index)) != index:
            raise ValueError(f"out-of-order control point {index}")
        for name in (
            "GantryPitchAngle",
            "TableTopPitchAngle",
            "TableTopRollAngle",
            "TableTopEccentricAngle",
        ):
            if _finite_float(getattr(cp, name, 0), name) % 360:
                raise ValueError(f"unsupported nonzero {name}")
        for name in (
            "TableTopVerticalPosition",
            "TableTopLongitudinalPosition",
            "TableTopLateralPosition",
        ):
            value = getattr(cp, name, None)
            if value not in (None, ""):
                value = _finite_float(value, name)
                if index and table_positions.get(name) != value:
                    raise ValueError(f"unsupported changing {name}")
                table_positions[name] = value
        if hasattr(cp, "IsocenterPosition") or iso is None:
            iso = _values(
                getattr(cp, "IsocenterPosition", None), 3, "IsocenterPosition"
            )
        angles = []
        for axis, (name, direction_name, increasing) in enumerate(_ANGLES):
            raw = getattr(cp, name, None)
            if raw is None and points:
                target = points[-1].angles[axis] % 360
            else:
                target = _finite_float(raw, name)
            if points:
                previous = points[-1].angles[axis]
                direction = directions[axis]
                # An omitted direction can describe a fixed angle only.
                target = _advance_angle(
                    previous, target, direction or "NONE", increasing
                )
            angles.append(target)
            if hasattr(cp, direction_name):
                directions[axis] = str(getattr(cp, direction_name))
        updated = set()
        for item in getattr(cp, "BeamLimitingDevicePositionSequence", []):
            kind = str(getattr(item, "RTBeamLimitingDeviceType", ""))
            if kind not in devices or kind in updated:
                raise ValueError(
                    f"unexpected {kind!r} positions at control point {index}"
                )
            updated.add(kind)
            tips[kind] = _values(
                getattr(item, "LeafJawPositions", None),
                2 * devices[kind].pairs,
                kind + " positions",
            )
        if tips.keys() != devices.keys():
            raise ValueError(
                f"missing initial device positions for {', '.join(sorted(devices.keys() - tips.keys()))}"
            )
        points.append(ControlPoint(iso, tuple(angles), tips.copy()))
    if len(points) < 2 or len(points) != int(
        getattr(beam, "NumberOfControlPoints", len(points))
    ):
        raise ValueError("empty or incomplete ControlPointSequence")
    return points


def _setup(dataset, beam, warnings):
    setups = getattr(dataset, "PatientSetupSequence", [])
    reference = getattr(beam, "ReferencedPatientSetupNumber", None)
    if reference is not None:
        setups = [
            s for s in setups if getattr(s, "PatientSetupNumber", None) == reference
        ]
        if not setups:
            raise ValueError(f"patient setup {reference} was not found")
    codes = {str(getattr(s, "PatientPosition", "")) for s in setups}
    if len(codes) > 1:
        raise ValueError("ambiguous patient setup")
    position = next(iter(codes), "")
    if not position:
        warnings.append("patient position missing, HFS assumed")
        position = "HFS"
    if position[:2] not in ("HF", "FF") or position[2:] not in _SETUP_ROLL:
        raise ValueError(f"unsupported patient position {position}")
    return position


def _curve(obj, path, axis, frames, values, interpolation="LINEAR"):
    """Insert a complete channel at once, avoiding per-key action updates."""
    anim = obj.animation_data_create()
    if anim.action is None:
        anim.action = bpy.data.actions.new(obj.name)
    curve = anim.action.fcurve_ensure_for_datablock(obj, path, index=axis)
    keys = curve.keyframe_points
    keys.add(len(frames))
    keys.foreach_set(
        "co", [v for pair in zip(frames, values, strict=True) for v in pair]
    )
    for key in keys:
        key.interpolation = interpolation
    curve.update()
    curve.update_autoflags(obj)


def _animate_axis(obj, path, axis, frames, values):
    values = list(values)
    getattr(obj, path)[axis] = values[0]
    if any(value != values[0] for value in values):
        _curve(obj, path, axis, frames, values)


def _new_object(collection, name, parent=None, mesh=None):
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.parent = parent
    if mesh is None:
        obj.empty_display_size = 0.02
    return obj


def _build_beam(
    collection, mesh, devices, points, setup, frames, ct, patient_to_world, visibility
):
    iso = _new_object(collection, collection.name + " Isocentre", ct)
    if ct is not None:
        # Keep the full affine transform (also for oblique, scaled CTs).
        iso.matrix_parent_inverse = ct.matrix_world.inverted() @ patient_to_world
    for axis in range(3):
        _animate_axis(
            iso, "location", axis, frames, (p.isocentre[axis] / 1000 for p in points)
        )
    setup_rotation = Matrix.Rotation(math.radians(_SETUP_ROLL[setup[2:]]), 4, "Z")
    if setup.startswith("FF"):
        setup_rotation = setup_rotation @ Matrix.Rotation(math.pi, 4, "Y")
    iso.rotation_euler = setup_rotation.to_euler()

    couch = _new_object(collection, "Patient support", iso)
    gantry = _new_object(collection, "Gantry", couch)
    basis = _new_object(collection, "IEC beam axes", gantry)
    basis.matrix_basis = IEC_BEAM_TO_DICOM
    collimator = _new_object(collection, "Collimator", basis)
    for obj, axis, angle_index in ((couch, 1, 2), (gantry, 2, 0), (collimator, 2, 1)):
        _animate_axis(
            obj,
            "rotation_euler",
            axis,
            frames,
            (math.radians(p.angles[angle_index]) for p in points),
        )

    # Only the inner edges are specified. Make the illustrative bodies long
    # enough to span the largest field or offset in this beam (projected mm).
    boundary_extent = max(
        (abs(v) for d in devices.values() for v in d.boundaries), default=0
    )
    tip_extent = max(abs(v) for p in points for tips in p.tips.values() for v in tips)
    extent = max(10.0, boundary_extent, tip_extent)
    for d in devices.values():
        axis = _DEVICE_AXES[d.kind]
        for index in range(2 * d.pairs):
            pair = index % d.pairs
            bank = index // d.pairs
            low, high = (
                d.boundaries[pair : pair + 2] if d.boundaries else (-extent, extent)
            )
            leaf = _new_object(
                collection, f"{d.kind} {'AB'[bank]}{pair + 1:03}", collimator, mesh
            )
            leaf.scale[axis] = 2 * extent * d.scale
            leaf.scale[1 - axis] = (high - low) * d.scale
            leaf.location[1 - axis] = (low + high) * 0.5 * d.scale
            leaf.location.z = d.height
            offset = extent if bank else -extent
            _animate_axis(
                leaf,
                "location",
                axis,
                frames,
                ((p.tips[d.kind][index] + offset) * d.scale for p in points),
            )
            if visibility:
                times, hidden = zip(*visibility, strict=True)
                for prop in ("hide_viewport", "hide_render"):
                    _curve(leaf, prop, 0, times, hidden, "CONSTANT")


def _build_plan(plan, mesh, beams, ct, transform, frame):
    mesh.from_pydata(
        [(-0.5, -0.5, 0), (0.5, -0.5, 0), (0.5, 0.5, 0), (-0.5, 0.5, 0)],
        [],
        [(0, 1, 2, 3)],
    )
    for i, (label, devices, points, setup) in enumerate(beams):
        collection = bpy.data.collections.new(label)
        plan.children.link(collection)
        frames = [frame]
        for previous, current in zip(points, points[1:], strict=False):
            sweep = max(
                abs(a - b) for a, b in zip(previous.angles, current.angles, strict=True)
            )
            frames.append(frames[-1] + max(4, math.ceil(sweep / 3)))
        visibility = []
        if i:
            visibility.extend([(frame - 1, True), (frame, False)])
        if i < len(beams) - 1:
            visibility.extend([(frames[-1], False), (frames[-1] + 1, True)])
        _build_beam(
            collection, mesh, devices, points, setup, frames, ct, transform, visibility
        )
        collection["medblend_control_point_frames"] = frames
        frame = frames[-1] + 1
    return frame - 1


def load_photon_plan(file_path: Path) -> bool:
    try:
        ds = pydicom.dcmread(file_path)
    except Exception as exc:
        show_message_box(f"Unable to read file: {exc}", "Photon Plan", "ERROR")
        return False
    if str(getattr(ds, "SOPClassUID", "")) != pydicom.uid.RTPlanStorage or not getattr(
        ds, "BeamSequence", None
    ):
        show_message_box(
            "Select a conventional DICOM RT Plan with external beams.",
            "Photon Plan",
            "ERROR",
        )
        return False

    if getattr(ds, "RTPlanGeometry", "PATIENT") != "PATIENT":
        show_message_box(
            "The plan has no patient-based geometry.", "Photon Plan", "ERROR"
        )
        return False

    warnings = []
    beams = []
    for i, beam in enumerate(ds.BeamSequence, 1):
        label = f"Beam {getattr(beam, 'BeamNumber', i)} {getattr(beam, 'BeamName', '')}".strip()
        if getattr(beam, "TreatmentDeliveryType", "") in (
            "SETUP",
            "OPEN_PORTFILM",
            "TRMT_PORTFILM",
        ):
            continue
        notes = []
        try:
            if getattr(beam, "RadiationType", "") != "PHOTON":
                raise ValueError("not a photon beam")
            if (
                getattr(beam, "EnhancedRTBeamLimitingDeviceDefinitionFlag", "NO")
                == "YES"
            ):
                raise ValueError(
                    "enhanced beam limiting device definitions are unsupported"
                )
            setup = _setup(ds, beam, notes)
            devices = _devices(beam, notes)
            points = _control_points(beam, devices)
        except (ValueError, TypeError, OverflowError) as exc:
            warnings.append(f"{label} skipped: {exc}")
            continue
        warnings.extend(f"{label}: {note}" for note in notes)
        beams.append((label, devices, points, setup))

    if not beams:
        show_message_box(
            "No photon beams imported.\n" + "\n".join(warnings[:3]),
            "Photon Plan",
            "ERROR",
        )
        return False

    scene = bpy.context.scene
    uid = str(getattr(ds, "FrameOfReferenceUID", ""))
    ct = find_ct_anchor(uid) if uid else None
    transform = ct_patient_to_world(ct) if ct is not None else None
    if ct is not None and (
        transform is None or ct.matrix_world.to_3x3().determinant() == 0
    ):
        show_message_box(
            "Cannot register the plan to the matching CT geometry.",
            "Photon Plan",
            "ERROR",
        )
        return False
    plan = bpy.data.collections.new(
        "Photon Plan " + str(getattr(ds, "RTPlanLabel", ""))
    )
    scene.collection.children.link(plan)
    mesh = bpy.data.meshes.new("Photon aperture rectangle")
    try:
        last_frame = _build_plan(plan, mesh, beams, ct, transform, scene.frame_start)
    except Exception as exc:
        # Remove only datablocks allocated for this import. Re-running the
        # operator after an error must not leave extra animated appliances.
        for obj in list(plan.all_objects):
            action = obj.animation_data.action if obj.animation_data else None
            bpy.data.objects.remove(obj, do_unlink=True)
            if action and not action.users:
                bpy.data.actions.remove(action)
        for child in list(plan.children):
            bpy.data.collections.remove(child)
        bpy.data.collections.remove(plan)
        bpy.data.meshes.remove(mesh)
        show_message_box(
            f"Could not build photon animation: {exc}", "Photon Plan", "ERROR"
        )
        return False

    scene.frame_end = max(scene.frame_end, last_frame)
    scene.frame_set(scene.frame_start)
    if warnings:
        plan["medblend_import_notes"] = "\n".join(warnings)
        for warning in warnings:
            print(f"MedBlend: {warning}")
        show_message_box(
            "\n".join(warnings[:3])
            + (" (more in console)" if len(warnings) > 3 else ""),
            "Photon Import Notes",
            "INFO",
        )
    return True
