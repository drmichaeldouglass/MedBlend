import bpy
import pydicom
import numpy as np

ds = pydicom.dcmread("C:\MedBlend\Rando Test Files\Xray\CT\RP1.2.752.243.1.1.20230109113526003.1830.31818.dcm")
print('Start Here')
beam_num = 0
#MLC_positions_all = []
for beam in ds.BeamSequence:
    mlc_positions = []
    for cp in beam.ControlPointSequence:
            if int(cp.ControlPointIndex) == 0:
                mlc_positions.append(cp.BeamLimitingDevicePositionSequence[2].LeafJawPositions)
            else:
                mlc_positions.append(cp.BeamLimitingDevicePositionSequence[0].LeafJawPositions)
    
    break     
mlc_positions = np.asarray(mlc_positions)
#    mlc_positions = np.array(mlc_positions)
    
    # Animate the cubes using the MLC position data
for MLC_Number in range(0,mlc_positions.shape[1]):
    print('Test2)')
    bpy.ops.mesh.primitive_cube_add(scale=(1,10,1), location=(np.mod(MLC_Number,60), MLC_Number//60, 0))
    for frame in range(0,mlc_positions.shape[0]):
        print('Test1')
        bpy.context.object.location.y = mlc_positions[frame,MLC_Number]
        bpy.context.object.keyframe_insert(data_path="location", frame=frame)
#beam_num = beam_num + 1   


