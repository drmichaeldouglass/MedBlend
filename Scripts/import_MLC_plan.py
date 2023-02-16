import bpy 
import numpy as np
import pydicom 




filepath = r"C:\plan.dcm"


dcm = pydicom.dcmread(filepath) 


# Get the MLC position data 

mlc_positions = dcm.BeamSequence[0].ControlPointSequence[0].BeamLimitingDevicePositionSequence[2].LeafJawPositions 
mlc_positions = np.asarray(mlc_positions)

#print(mlc_positions)

# Create an empty object to hold the MLC animation 

mlc_animation = bpy.data.objects.new("MLC Animation", None) 

bpy.context.scene.collection.objects.link(mlc_animation) 


# Set the frame range to match the number of control points 

num_control_points = len(dcm.BeamSequence[0].ControlPointSequence) 

bpy.context.scene.frame_start = 1 

bpy.context.scene.frame_end = num_control_points 


# Create a curve for each MLC leaf 

num_leaves = len(mlc_positions) // 2 

for i in range(num_leaves): 

    curve = bpy.data.curves.new("MLC Leaf {}".format(i), type='CURVE') 

    curve.dimensions = '3D' 

    curve_obj = bpy.data.objects.new("MLC Leaf {}".format(i), curve) 

    curve_obj.parent = mlc_animation 

    bpy.context.scene.collection.objects.link(curve_obj) 


    # Create a spline for the curve 

    spline = curve.splines.new('BEZIER') 

    spline.bezier_points.add(num_control_points - 1) 


    # Set the control points for the spline 

    for j, mlc_position in enumerate(mlc_positions): 
        
        print(mlc_position)
        x = mlc_position

        y = i 

        z = 0 

        spline.bezier_points[j].co = (x, y, z) 
