import bpy
import pydicom
import numpy as np

# Create 120 empty objects for each MLC leaf
for i in range(1, 61):
    bpy.ops.object.empty_add(location=(0, 0, 0))
    bpy.context.active_object.name = f"control_A_L_{i}"
    
    bpy.ops.object.empty_add(location=(0, 0, 0))
    bpy.context.active_object.name = f"control_B_L_{i}"

# Read the DICOM file
ds = pydicom.dcmread(r"./plan.dcm")

for beam in ds.BeamSequence:
    mlc_positions = []
    for cp in beam.ControlPointSequence:
        if int(cp.ControlPointIndex) == len(beam.ControlPointSequence)-1:
            break
        if int(cp.ControlPointIndex) == 0:
            mlc_positions.append(cp.BeamLimitingDevicePositionSequence[2].LeafJawPositions)
        else:
            mlc_positions.append(cp.BeamLimitingDevicePositionSequence[0].LeafJawPositions)
    
    break     

mlc_positions = np.asarray(mlc_positions)
print(mlc_positions.shape)
# Animate the empty objects using the MLC position data
for MLC_Number in range(0, mlc_positions.shape[1]):
    # Determine the MLC leaf name based on the MLC_Number
    if MLC_Number < 60:
        mlc_name = f"control_A_L_{MLC_Number+1}"
    else:
        mlc_name = f"control_B_L_{MLC_Number-59}"

    # Get the MLC leaf object
    mlc_leaf = bpy.data.objects[mlc_name]

    for frame in range(0, mlc_positions.shape[0]):
        # Set the MLC leaf position
        mlc_leaf.location.x = -mlc_positions[frame, MLC_Number]
        # Insert a keyframe for the current frame
        mlc_leaf.keyframe_insert(data_path="location", frame=frame, index=1)
        #print(frame)