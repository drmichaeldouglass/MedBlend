import bpy
import pydicom
import numpy as np




def make_mlc_leaf(MLC_index = 1):
    # Set the dimensions of the cube
    x_dim = 2
    y_dim = 40
    z_dim = 1
    
    # Create a cube and set its dimensions
    bpy.ops.mesh.primitive_cube_add(size=1)
    cube = bpy.context.active_object
    cube.dimensions = (x_dim, y_dim, z_dim)
    
    # Move the origin point to the end of the cube
    
    # Enter edit mode
    bpy.ops.object.mode_set(mode='EDIT')

    # Move the selected object by 5 meters in the Y direction
    if MLC_index <= 59:
        
        bpy.ops.transform.translate(value=(0, y_dim/2, 0))
    else:
        bpy.ops.transform.translate(value=(0, -y_dim/2, 0))
        

    # Re-enter object mode
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    bpy.context.object.location[0] = np.mod(MLC_index,60)*x_dim
    #bpy.context.object.location[1] = MLC_index//60


ds = pydicom.dcmread("C:\MedBlend\Rando Test Files\Xray\CT\RP1.2.752.243.1.1.20230109113526003.1830.31818.dcm")
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
        
            bpy.context.object.location.y = -mlc_positions[frame,MLC_Number]
        else:
            bpy.context.object.location.y = -mlc_positions[frame,MLC_Number]
       
        
        bpy.context.object.keyframe_insert(data_path="location", frame=frame)
#beam_num = beam_num + 1   

