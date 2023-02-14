import bpy 
import numpy as np
import pydicom 


filepath = r"PATH_TO_PLAN"



# Read the DICOM file and get the spot positions and weights 

dataset = pydicom.dcmread(filepath) 


control_points = dataset.IonBeamSequence[0].IonControlPointSequence
num_control_points = len(control_points)

spots = []
for i in range(0, num_control_points, 2): 
    spots_in_energy_layer = len(dataset.IonBeamSequence[0].IonControlPointSequence[i].ScanSpotPositionMap)
    weights = control_points[i].ScanSpotMetersetWeights
    for j in range(0,spots_in_energy_layer,2):

            x = control_points[i].ScanSpotPositionMap[j]

            y = control_points[i].ScanSpotPositionMap[j+1]

            E = control_points[i].NominalBeamEnergy
            
            print(x,y,E)
            if weights[int(j/2)]>0:
                
                bpy.ops.mesh.primitive_uv_sphere_add(location=(x,y,E), radius=weights[int(j/2)]/10)
            
            #spots.append((x, y,E))
    
#spots = np.asarray(spots)
#print(spots)


#for k in range(0,len(spots)):
#    bpy.ops.mesh.primitive_uv_sphere_add(location=(spots[0],spots[1],spots[2]), radius=weights[0])
            
