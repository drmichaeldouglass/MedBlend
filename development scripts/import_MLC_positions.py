import bpy
import pydicom
import numpy as np




def make_mlc_leaf(MLC_index = 1):
    # Set the dimensions of the cube
    x_dim = 2
    y_dim = 40
    z_dim = 1
    
    # Create an empty object
    bpy.ops.object.empty_add(location=(0, 0, 0))
    empty = bpy.context.active_object
    
    # Move the origin point to the end of the empty object
    if MLC_index <= 59:
        empty.location.y = y_dim/2
    else:
        empty.location.y = -y_dim/2

    empty.location.x = np.mod(MLC_index,60)*x_dim


ds = pydicom.dcmread(r"./plan.dcm")
beam_num = 0
#MLC_positions_all = []
for beam in ds.BeamSequence:
    mlc_positions = []
    for cp in beam.ControlPointSequence:
            print(int(cp.ControlPointIndex))
            if int(cp.ControlPointIndex) == len(beam.ControlPointSequence)-1:
                break
            if int(cp.ControlPointIndex) == 0:
                mlc_positions.append(cp.BeamLimitingDevicePositionSequence[2].LeafJawPositions)
            else:
                mlc_positions.append(cp.BeamLimitingDevicePositionSequence[0].LeafJawPositions)
    
    break     
mlc_positions = np.asarray(mlc_positions)
#    mlc_positions = np.array(mlc_positions)
    
    # Animate the cubes using the MLC position data
for MLC_Number in range(0,mlc_positions.shape[1]):
    #bpy.ops.mesh.primitive_cube_add(scale=(0.5,10,1), location=(np.mod(MLC_Number,60), MLC_Number//60, 0))
    make_mlc_leaf(MLC_index = MLC_Number)
    for frame in range(0,mlc_positions.shape[0]):
        
        if MLC_Number <= 59:
        
            bpy.context.object.location.y = -mlc_positions[frame,MLC_Number]/2
        else:
            bpy.context.object.location.y = -mlc_positions[frame,MLC_Number]/2
       
        
        bpy.context.object.keyframe_insert(data_path="location", frame=frame)
#beam_num = beam_num + 1   

