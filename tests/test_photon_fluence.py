"""Independent point values in millimetres and normalised fluence units."""

from types import SimpleNamespace as NS

import numpy as np
import pytest

from MedBlend.photon_fluence import PatientGrid, _beam_shares, _deliveries, _snapshots
from MedBlend.photon_plan import ControlPoint, Device


def delivery(weights, fields, *, kind="MLCX", angles=None, final=None):
    devices = {
        kind: Device(kind, 2, (-12, -2, 14), 0.0005, 0.05),
        "ASYMY": Device("ASYMY", 1, (), 0.0004, 0.06),
    }
    angles = angles or [(0, 0, 0)] * len(weights)
    points = [
        ControlPoint((1.5, 2.5, 3.5), angle, {kind: tips, "ASYMY": (-7, 7)})
        for angle, tips in zip(angles, fields, strict=True)
    ]
    source = NS(
        SourceAxisDistance=100,
        ControlPointSequence=[NS(CumulativeMetersetWeight=w) for w in weights],
        FinalCumulativeMetersetWeight=weights[-1] if final is None else final,
    )
    return _deliveries(NS(), [source], [("beam", devices, points, "HFS")], 10)[0]


def voxel(grid, offset):
    point = np.array((1.5, 2.5, 3.5)) + offset
    index = np.rint((point - grid.origin) / grid.spacing).astype(int)
    return grid.values[tuple(index)]


def test_static_aperture_jaws_divergence_and_zero_weight_motion():
    opened = (-8, -4, 8, 4)
    closed = (0, 0, 0, 0)
    beam = delivery([0, 25, 25, 100], [opened, opened, closed, closed])
    grid = PatientGrid([beam], 1)
    # Three prescribed segments, each taking four display frames.
    for frame, _ in _snapshots([beam], grid, [10, 12, 14, 18, 22]):
        weight = 0.125 if frame == 12 else 0.25
        assert voxel(grid, (0, 0, 0)) == pytest.approx(weight)
        assert voxel(grid, (6, 0, -5)) == pytest.approx(weight)  # wider lower leaf row
        assert voxel(grid, (6, 0, 0)) == 0
        assert voxel(grid, (0, 0, 9)) == 0  # Y jaw
        assert voxel(grid, (0, -50, 0)) == pytest.approx(4 * weight)
        assert voxel(grid, (3, -50, 0)) == 0  # upper opening is only +/-2 mm here
        assert voxel(grid, (0, -51, 0)) == 0  # upstream of MLC
        assert voxel(grid, (0, 1, 0)) == 0  # beyond isocentre


def test_rotating_beam_and_sliding_leaves_accumulate_in_patient_coordinates():
    left = (-10, -10, -2, -2)
    right = (2, 2, 10, 10)
    beam = delivery([0, 1], [left, right], kind="MLCY")
    grid = PatientGrid([beam], 1)
    list(_snapshots([beam], grid, [10, 14]))
    # Centre exposed for 2/3 of a linear leaf sweep, both endpoint apertures miss it.
    assert voxel(grid, (0, 0, 0)) == pytest.approx(2 / 3, abs=0.04)
    opened = (-8, -8, 8, 8)
    arc = delivery([0, 1], [opened, opened], angles=[(0, 0, 0), (90, 0, 0)])
    grid = PatientGrid([arc], 2)
    snapshots = _snapshots([arc], grid, [10, 25, 40])
    next(snapshots)
    early = voxel(grid, (0, -40, 0))
    assert early > 0 and voxel(grid, (40, 0, 0)) == 0
    next(snapshots)
    assert voxel(grid, (0, -40, 0)) == early
    assert voxel(grid, (40, 0, 0)) > 0
    assert voxel(grid, (0, 0, 0)) == pytest.approx(1)


def test_fraction_group_relative_metersets_and_invalid_inputs():
    refs = [
        NS(ReferencedBeamNumber=2, BeamMeterset=75),
        NS(ReferencedBeamNumber=1, BeamMeterset=25),
    ]
    ds = NS(FractionGroupSequence=[NS(ReferencedBeamSequence=refs)])
    beams = [NS(BeamNumber=i) for i in [1, 2, 3]]
    assert list(_beam_shares(ds, beams)) == [0.25, 0.75, 0]
    with pytest.raises(ValueError, match="combining beams"):
        _beam_shares(NS(), beams)
    ds.FractionGroupSequence *= 2
    with pytest.raises(ValueError, match="multiple fraction groups"):
        _beam_shares(ds, beams)
    field = (-8, -8, 8, 8)
    for weights, final in [([0, 1, 0.5], 0.5), ([1, 2], 2), ([0, 2], 100), ([0, 0], 0)]:
        with pytest.raises(ValueError, match="meterset"):
            delivery(weights, [field] * len(weights), final=final)
