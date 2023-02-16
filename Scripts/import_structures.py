import bpy 

import pydicom 


filepath = r"D:\Test Files\RS1.2.752.243.1.1.20230109113525642.1810.76676.dcm"

dicom_data = pydicom.dcmread(filepath) 


# Extract the contour data from the structure file 

contours = [] 
structure_name = []
for i,structure in enumerate(dicom_data.ROIContourSequence): 
    points = [] 
    structure_name.append(dicom_data.StructureSetROISequence[i].ROIName)
    for contour in structure.ContourSequence: 

        

        for i in range(0, len(contour.ContourData), 3): 

            x = contour.ContourData[i+2]/1000

            y = contour.ContourData[i+1]/1000

            z = contour.ContourData[i]/1000

            points.append((x, y, z)) 

    contours.append(points) 


# Convert the contours into mesh objects 
bpy.ops.object.select_all(action='DESELECT')  
for j,contour in enumerate(contours):  

    mesh = bpy.data.meshes.new(name="DICOM Structure") 

    mesh.from_pydata(contour, [], []) 

    object = bpy.data.objects.new(structure_name[j], mesh)
    
    
    bpy.context.collection.objects.link(object)
    bpy.data.objects[object.name].select_set(True)
    bpy.context.view_layer.objects.active = object

  

#bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='MEDIAN')
#bpy.context.object.location = (0.0, 0.0, 0.0)
