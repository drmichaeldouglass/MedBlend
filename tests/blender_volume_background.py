"""Run inside Blender with the packaged extension enabled (see extension.yml).

Checks, against the OpenVDB module Blender ships, that an image volume is
written with its lowest intensity as the grid background.
"""

import numpy as np

import bpy
from bl_ext.user_default.medblend.volume_utils import (
    _import_openvdb_module,
    write_vdb_volume,
)

AIR = -1000.0

voxels = np.full((6, 7, 8), AIR, dtype=np.float32)
voxels[2:4, 2:5, 3:6] = 40.0
voxels[3, 3, 4] = 0.0

errors = []
result = write_vdb_volume(
    voxels, (2.0, 1.0, 1.0), "background_check.vdb", on_error=errors.append, background=AIR
)
assert result is not None, errors
path, obj = result
assert obj.type == "VOLUME"

grid = _import_openvdb_module().read(str(path), "density")
accessor = grid.getAccessor()
assert grid.background == AIR, grid.background
# Far outside the array the grid reads as air rather than as 0 HU water.
assert accessor.getValue((500, 500, 500)) == AIR
assert accessor.getValue((0, 0, 0)) == AIR
assert accessor.getValue((2, 2, 3)) == 40.0
# A voxel of exactly 0 HU is data here, not background, and must stay active.
assert accessor.getValue((3, 3, 4)) == 0.0
assert accessor.isValueOn((3, 3, 4))
# Only the voxels that differ from air are stored as active.
assert grid.activeVoxelCount() == int(np.count_nonzero(voxels != AIR))

bpy.data.objects.remove(obj, do_unlink=True)
path.unlink(missing_ok=True)
print("Volume background check passed")
