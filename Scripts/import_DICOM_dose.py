import bpy
import pydicom
import os
import numpy as np
from pathlib import Path
import easybpy


#Directory containing DICOM images
DICOM_dir = dose_dir

file_path = Path(DICOM_dir)
root_dir = file_path.parents[0]

# Load the DICOM dataset
ds = pydicom.read_file(DICOM_dir) 

#Need to Check if DICOM is Dose
#if ds.Modality != 'RTDose':
#    print('Not a Dose DICOM')
#    exit() 


referenced_plan_file_UID = ds.ReferencedRTPlanSequence[0].ReferencedSOPInstanceUID

plan_file_name = root_dir.joinpath('RP' + referenced_plan_file_UID + '.dcm')

try:
    #loads matching plan if possible (not used yet)
    ds_plan = pydicom.read_file(plan_file_name)
except:
    print('No Plan File')
    

#Get the Dose Grid
pixel_data = ds.pixel_array 

dose_resolution = [ds.PixelSpacing[0]/1000, ds.PixelSpacing[1]/1000, ds.SliceThickness/1000] 

#CT origin coordinates
origin = np.asarray(ds.ImagePositionPatient)

#Converts list to numpy array
dose_matrix = np.asarray(pixel_data)
#Normalises the image volume in range 0,1
dose_matrix = dose_matrix/np.max(dose_matrix)

# Create an OpenVDB volume from the pixel data
import pyopenvdb as openvdb
#Creates a grid of Double precision
grid = openvdb.FloatGrid()
#Copies image volume from numpy to VDB grid
grid.copyFromArray(dose_matrix.astype(float))

#Scales the grid to slice thickness and pixel size using modified identity transformation matrix. NB. Blender is Z up coordinate system
grid.transform = openvdb.createLinearTransform([[dose_resolution[2], 0, 0, 0], [0, dose_resolution[0], 0, 0], [0,0,dose_resolution[1],0], [0,0,0,1]])
#Sets the grid class to FOG_VOLUME
grid.gridClass = openvdb.GridClass.FOG_VOLUME
#Blender needs grid name to be "Density"
grid.name='density'

dose_dir = root_dir.joinpath('dose.vdb')
#Writes CT volume to a vdb file but perhaps this could be done internally in the future
openvdb.write(str(dose_dir),grid)

# Add the volume to the scene
bpy.ops.object.volume_import(filepath=str(dose_dir), files=[])
DICOM_object = easybpy.get_selected_object()
# Set the volume's origin to match the DICOM image position
#bpy.context.object.location = origin/1000
