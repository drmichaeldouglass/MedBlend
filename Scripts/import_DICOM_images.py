import bpy
import pydicom
import os
import numpy as np

#Directory containing DICOM images
DICOM_dir = r"PATH_TO_DICOM_FILES"

##Finds all files with .dcm extension
#image_files = [f for f in os.listdir(DICOM_dir) if f.endswith('.dcm')]


#Consider saving the DICOM images during the sorting loop to save time reading them in again
def get_dicom_file_paths(directory):
    file_paths = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".dcm"):
                file_paths.append(os.path.join(root, file))
    return file_paths

def sort_dicom_files(file_paths):
    return sorted(file_paths, key=lambda x: pydicom.dcmread(x).InstanceNumber)

dicom_file_paths = get_dicom_file_paths(DICOM_dir)
image_files = sort_dicom_files(dicom_file_paths)





#creates an empty array to hold CT image slices
image_planes = []


for image_file in image_files:
    
    # Load the DICOM dataset
    ds = pydicom.read_file(image_file) 
    
    if (ds.Modality != 'CT'):
        continue
    
    # Extract the pixel data and metadata
    pixel_data = ds.pixel_array
    
    #Pixel spacing in X,Y direction
    spacing = ds.PixelSpacing
    
    #CT origin coordinates
    origin = np.asarray(ds.ImagePositionPatient)
    
    #Adds current CT slice to image volume
    image_planes.append(pixel_data)

#Gets total number of CT slices
num_slices = len(image_planes)

#Gets the slice thickness
slice_spacing = ds.SliceThickness

#Converts slice spacing from string to float
slice_spacing = np.asarray(slice_spacing)

#Converts list to numpy array
image_planes = np.asarray(image_planes)
#Normalises the image volume in range 0,1
image_planes = image_planes/np.max(image_planes)




# Create an OpenVDB volume from the pixel data
import pyopenvdb as openvdb
#Creates a grid of Double precision
grid = openvdb.DoubleGrid()
#Copies image volume from numpy to VDB grid
grid.copyFromArray(image_planes.astype(float))

#Scales the grid to slice thickness and pixel size using modified identity transformation matrix. NB. Blender is Z up coordinate system
grid.transform = openvdb.createLinearTransform([[slice_spacing/100, 0, 0, 0], [0, spacing[0]/100, 0, 0], [0,0,spacing[1]/100,0], [0,0,0,1]])

#Sets the grid class to FOG_VOLUME
grid.gridClass = openvdb.GridClass.FOG_VOLUME
#Blender needs grid name to be "Density"
grid.name='density'

#Writes CT volume to a vdb file but perhaps this could be done internally in the future
openvdb.write(DICOM_dir + "CT.vdb",grid)

# Add the volume to the scene
bpy.ops.object.volume_import(filepath=DICOM_dir + "CT.vdb", files=[])

# Set the volume's origin to match the DICOM image position
print(origin)
bpy.context.object.location = origin/100
