"""Time-integrated ideal photon apertures on a patient-fixed voxel lattice."""

from __future__ import annotations

import math
from contextlib import ExitStack
from dataclasses import dataclass
from itertools import product
from uuid import uuid4

import bpy
import numpy as np
from mathutils import Matrix

from .photon_plan import _DEVICE_AXES, _beam_frames, _curve, _setup_rotation
from .plan import IEC_BEAM_TO_DICOM, _finite_float
from .volume_utils import write_vdb_volume


@dataclass
class Delivery:
    devices: dict
    points: list
    frames: list
    setup: Matrix
    sad: float
    height: float
    weights: np.ndarray


def _beam_shares(dataset, beams):
    """Relative beam metersets for one fraction. Never synthesize multi-beam weights."""
    groups = getattr(dataset, "FractionGroupSequence", [])
    if len(groups) > 1:
        raise ValueError(
            "multiple fraction groups; select a single-fraction-group plan"
        )
    if not groups:
        if len(beams) == 1:
            return [1.0]
        raise ValueError(
            "combining beams requires a fraction group with beam metersets"
        )
    refs = {}
    for ref in getattr(groups[0], "ReferencedBeamSequence", []):
        number = int(ref.ReferencedBeamNumber)
        if number in refs:
            raise ValueError(f"duplicate fraction group reference to beam {number}")
        refs[number] = ref
    numbers = [int(b.BeamNumber) for b in beams]
    if len(set(numbers)) != len(numbers):
        raise ValueError("duplicate photon beam numbers")
    values = []
    for number, beam in zip(numbers, beams, strict=True):
        if number not in refs:
            values.append(0.0)
            continue
        value = getattr(refs[number], "BeamMeterset", None)
        if len(beams) == 1 and value is None:
            value = 1.0
        value = _finite_float(value, f"Beam {number} BeamMeterset")
        if value < 0 or (value and getattr(beam, "PrimaryDosimeterUnit", "MU") != "MU"):
            raise ValueError(f"beam {number} requires a nonnegative MU meterset")
        values.append(value)
    total = sum(values)
    if not total or not math.isfinite(total):
        raise ValueError("no positive photon meterset in the fraction group")
    return np.asarray(values) / total


def _deliveries(ds, sources, beams, first_frame):
    deliveries = []
    for source, share, (_, devices, points, setup) in zip(
        sources, _beam_shares(ds, sources), beams, strict=True
    ):
        frames = _beam_frames(points, first_frame)
        first_frame = frames[-1] + 1
        if share == 0:
            continue
        sad = _finite_float(
            getattr(source, "SourceAxisDistance", None), "SourceAxisDistance"
        )
        height = min(d.height for d in devices.values()) * 1000
        if not 0 < height < sad:
            raise ValueError(
                "projection requires an aperture plane between source and isocentre"
            )
        if (
            not any(d.boundaries for d in devices.values())
            and len({_DEVICE_AXES[k] for k in devices}) != 2
        ):
            raise ValueError(
                "projection requires a field bounded in both transverse axes"
            )
        weights = np.array(
            [
                _finite_float(
                    getattr(cp, "CumulativeMetersetWeight", None),
                    "CumulativeMetersetWeight",
                )
                for cp in source.ControlPointSequence
            ]
        )
        final = _finite_float(
            getattr(source, "FinalCumulativeMetersetWeight", weights[-1]),
            "FinalCumulativeMetersetWeight",
        )
        if (
            weights[0] != 0
            or final <= 0
            or not np.isclose(weights[-1], final, rtol=1e-6, atol=0)
            or np.any(np.diff(weights) < 0)
        ):
            raise ValueError("inconsistent or decreasing cumulative meterset weights")
        deliveries.append(
            Delivery(
                devices,
                points,
                frames,
                _setup_rotation(setup),
                sad,
                height,
                share * (weights / final),
            )
        )
    return deliveries


def _aperture_bounds(devices, tips):
    """Intersection of device bounding rectangles, in projected millimetres."""
    low = np.full(2, -np.inf)
    high = np.full(2, np.inf)
    for kind, device in devices.items():
        axis = _DEVICE_AXES[kind]
        a, b = np.split(tips[kind], 2)
        opened = a < b
        if not np.any(opened):
            return None
        low[axis] = max(low[axis], a[opened].min())
        high[axis] = min(high[axis], b[opened].max())
        if device.boundaries:
            rows = np.flatnonzero(opened)
            low[1 - axis] = max(low[1 - axis], device.boundaries[rows[0]])
            high[1 - axis] = min(high[1 - axis], device.boundaries[rows[-1] + 1])
    return (low, high) if np.all(low < high) else None


def _rotation(setup, angles):
    gantry, collimator, couch = np.radians(angles)
    matrix = (
        setup
        @ Matrix.Rotation(couch, 4, "Y")
        @ Matrix.Rotation(gantry, 4, "Z")
        @ IEC_BEAM_TO_DICOM
        @ Matrix.Rotation(collimator, 4, "Z")
    )
    return np.array([row[:3] for row in matrix[:3]])


class PatientGrid:
    def __init__(self, deliveries, spacing):
        # Anchor the lattice to the first isocentre so its centre is sampled
        # even for non-integral DICOM isocentre coordinates.
        self.spacing = spacing
        anchor = np.asarray(deliveries[0].points[0].isocentre)
        lows, highs = [], []
        for beam in deliveries:
            extent = max(
                abs(v) for p in beam.points for tips in p.tips.values() for v in tips
            )
            extent = max(
                extent,
                max(
                    (abs(v) for d in beam.devices.values() for v in d.boundaries),
                    default=0,
                ),
            )
            radius = math.hypot(beam.height, extent, extent)
            positions = np.array([p.isocentre for p in beam.points])
            lows.append(positions.min(axis=0) - radius)
            highs.append(positions.max(axis=0) + radius)
        low = np.floor((np.min(lows, axis=0) - anchor) / spacing)
        high = np.ceil((np.max(highs, axis=0) - anchor) / spacing)
        shape = tuple(int(n) for n in high - low + 1)
        if math.prod(shape) > 32_000_000:
            raise ValueError(
                "fluence grid exceeds 32 million voxels; increase Fluence Voxel Size"
            )
        self.origin = anchor + low * spacing
        self.values = np.zeros(shape, dtype=np.float32)
        self.low = np.array(shape)
        self.high = np.zeros(3, dtype=int)

    def project(self, beam, iso, rotation, tips, weight):
        bounds = _aperture_bounds(beam.devices, tips)
        if bounds is None:
            return
        corners = []
        for x, y, z in product(*zip(*bounds, strict=True), (0, beam.height)):
            scale = 1 - z / beam.sad
            corners.append(iso + rotation @ [x * scale, y * scale, z])
        indices = (np.array(corners) - self.origin) / self.spacing
        start = np.maximum(0, np.floor(indices.min(axis=0)).astype(int))
        stop = np.minimum(
            self.values.shape, np.ceil(indices.max(axis=0)).astype(int) + 1
        )
        self.low = np.minimum(self.low, start)
        self.high = np.maximum(self.high, stop)
        # Limit temporary arrays even for a broad field viewed obliquely.
        for x0 in range(start[0], stop[0], 12):
            region = (
                slice(x0, min(x0 + 12, stop[0])),
                slice(start[1], stop[1]),
                slice(start[2], stop[2]),
            )
            coords = [
                a * self.spacing + offset
                for a, offset in zip(np.ogrid[region], self.origin - iso, strict=True)
            ]
            x, y, z = (
                sum(c * r for c, r in zip(coords, column, strict=True))
                for column in rotation.T
            )
            # Coordinates use Blender's single-precision rotation matrices.
            opened = (z >= -1e-4) & (z <= beam.height + 1e-4)
            scale = beam.sad / (beam.sad - np.clip(z, 0, beam.height))
            projected = (x * scale, y * scale)
            for kind, device in beam.devices.items():
                axis = _DEVICE_AXES[kind]
                travel = projected[axis]
                a, b = np.split(tips[kind], 2)
                if device.boundaries:
                    row = (
                        np.searchsorted(
                            device.boundaries, projected[1 - axis], side="right"
                        )
                        - 1
                    )
                    opened &= (row >= 0) & (row < device.pairs)
                    row = np.clip(row, 0, device.pairs - 1)
                    opened &= (travel >= a[row]) & (travel < b[row])
                else:
                    opened &= (travel >= a[0]) & (travel < b[0])
            self.values[region] += opened * weight * scale**2

    def snapshot(self):
        if np.any(self.high <= self.low):
            return self.origin, self.values[:1, :1, :1]
        region = tuple(slice(a, b) for a, b in zip(self.low, self.high, strict=True))
        return self.origin + self.low * self.spacing, self.values[region]


def _snapshots(deliveries, grid, frames):
    """Integrate each segment to each requested boundary, yielding held states."""
    segments = [(beam, i) for beam in deliveries for i in range(len(beam.points) - 1)]
    cursor = 0
    previous = frames[0]
    for frame in frames[1:]:
        while cursor < len(segments):
            beam, i = segments[cursor]
            first, last = beam.frames[i : i + 2]
            if first >= frame:
                break
            start, stop = max(first, previous), min(frame, last)
            delta = beam.weights[i + 1] - beam.weights[i]
            if delta > 0 and stop > start:
                left, right = beam.points[i : i + 2]
                iso, angles = np.array(left.isocentre), np.array(left.angles)
                shift, sweep = right.isocentre - iso, right.angles - angles
                tips = {k: np.array(v) for k, v in left.tips.items()}
                moves = {k: right.tips[k] - v for k, v in tips.items()}
                fraction = (stop - start) / (last - first)
                travel = max(
                    np.linalg.norm(shift), *(np.max(abs(v)) for v in moves.values())
                )
                # Sample motion at half-voxel intervals, including gantry motion
                # near the device plane where an angular step sweeps furthest.
                radius = math.hypot(
                    beam.height, max(np.max(abs(v)) for v in tips.values())
                )
                travel += radius * np.radians(np.abs(sweep).sum())
                count = max(1, math.ceil(2 * travel * fraction / grid.spacing))
                for j in range(count):
                    t = (start - first) / (last - first) + (j + 0.5) / count * fraction
                    grid.project(
                        beam,
                        iso + t * shift,
                        _rotation(beam.setup, angles + t * sweep),
                        {k: v + t * moves[k] for k, v in tips.items()},
                        delta * fraction / count,
                    )
            if last > frame:
                break
            cursor += 1
        yield frame, grid.snapshot()
        previous = frame


def _configure_material(material):
    material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    volume = tree.nodes.new("ShaderNodeVolumePrincipled")
    density = tree.nodes.new("ShaderNodeVolumeInfo").outputs["Density"]
    gain = tree.nodes.new("ShaderNodeMath")
    gain.operation = "MULTIPLY"
    gain.inputs[1].default_value = 12
    tree.links.new(density, gain.inputs[0])
    volume.inputs["Density Attribute"].default_value = ""
    tree.links.new(gain.outputs[0], volume.inputs["Density"])
    tree.links.new(gain.outputs[0], volume.inputs["Emission Strength"])
    volume.inputs["Emission Color"].default_value = (0.08, 0.65, 1.0, 1.0)
    tree.links.new(volume.outputs["Volume"], output.inputs["Volume"])
    output.location = (480, 0)
    volume.location = (180, 0)
    gain.location = (-40, 0)
    density.node.location = (-260, 0)


def _remove_snapshot(obj):
    action = obj.animation_data.action if obj.animation_data else None
    bpy.data.objects.remove(obj, do_unlink=True)
    if action and not action.users:
        bpy.data.actions.remove(action)


def build_fluence(ds, sources, beams, plan, ct, transform, first, last, spacing, count):
    deliveries = _deliveries(ds, sources, beams, first)
    grid = PatientGrid(deliveries, spacing)
    frames = np.unique(
        np.linspace(first, last, min(count, last - first + 1)).round().astype(int)
    )
    token = uuid4().hex[:12]
    manager = bpy.context.window_manager
    manager.progress_begin(first, last)
    try:
        with ExitStack() as rollback:
            collection = bpy.data.collections.new("Cumulative Photon Fluence")
            rollback.callback(bpy.data.collections.remove, collection)
            plan.children.link(collection)
            material = bpy.data.materials.new("Cumulative photon fluence")
            rollback.callback(bpy.data.materials.remove, material)
            _configure_material(material)
            for frame, (origin, values) in _snapshots(deliveries, grid, frames):
                errors = []
                result = write_vdb_volume(
                    values,
                    (spacing,) * 3,
                    f"fluence_{token}_{frame}.vdb",
                    on_error=errors.append,
                )
                if result is None:
                    raise RuntimeError(" ".join(errors))
                path, obj = result
                rollback.callback(path.unlink, missing_ok=True)
                rollback.callback(bpy.data.volumes.remove, obj.data)
                rollback.callback(_remove_snapshot, obj)
                for parent in list(obj.users_collection):
                    parent.objects.unlink(obj)
                collection.objects.link(obj)
                obj.name = f"Fluence at frame {frame}"
                obj.parent = ct
                if ct is not None:
                    obj.matrix_parent_inverse = ct.matrix_world.inverted() @ transform
                obj.location = origin / 1000
                obj.data.materials.append(material)
                end = next((f for f in frames if f > frame), None)
                times, hidden = [frame - 1, frame], [True, False]
                if end is not None:
                    times.append(end)
                    hidden.append(True)
                for prop in ("hide_viewport", "hide_render"):
                    _curve(obj, prop, 0, times, hidden, "CONSTANT")
                manager.progress_update(int(frame))
            rollback.pop_all()
    finally:
        manager.progress_end()
