
# Import pydicom library
import pydicom
from pathlib import Path
import bpy
import os
import numpy as np

# Define a function to load DICOM images from a folder
def load_dicom_images(folder):
  # Create an empty list to store the images
  images = []
  # Loop through all files in the folder
  for filename in os.listdir(folder):
    # Check if the file is a DICOM file
    if filename.endswith(".dcm"):
      # Read the file using pydicom
      image = pydicom.dcmread(os.path.join(folder, filename))
      # Append the image to the list
      images.append(image)
  # Return the list of images
  return images

# Define a function to filter DICOM images by series UID
def filter_by_series_uid(images, series_uid):
  # Create an empty list to store the filtered images
  filtered_images = []
  # Loop through all images in the list
  for image in images:
    # Check if the image has the same series UID as specified
    if image.SeriesInstanceUID == series_uid:
      # Append the image to the filtered list
      filtered_images.append(image)
  # Return the filtered list of images
  return filtered_images

# Define a function to sort DICOM images by instance number
def sort_by_instance_number(images):
  # Sort the list of images by their instance number attribute using lambda function
  sorted_images = sorted(images, key=lambda x: x.InstanceNumber)
  # Return the sorted list of images
  return sorted_images

def extract_dicom_pixels(images):
  
  dicom_3d_array = []
  
  for i in range(0,len(sorted_images)):
      dicom_3d_array.append(images[i].pixel_array)       
  dicom_3d_array = np.asarray(dicom_3d_array)    
  return dicom_3d_array



# Specify your folder path and series UID here (example values are given)
file = "C:\MedBlend\MedBlend\Rando Test Files\CT\CT1.2.752.243.1.1.20230109113524900.2000.30302.dcm"

selected_file = pydicom.dcmread(file)


series_uid = selected_file.SeriesInstanceUID

dir_path = Path(file)
dir_path = dir_path.parents[0]


# Load all DICOM CT images from your folder using load_dicom_images function
images = load_dicom_images(dir_path)

# Filter out only those DICOM CT images that have your specified series UID using filter_by_series_uid function
filtered_images = filter_by_series_uid(images, series_uid)

# Sort those filtered DICOM CT slices by their instance number using sort_by_instance_number function
sorted_images = sort_by_instance_number(filtered_images)

CT_volume = extract_dicom_pixels(sorted_images)

print(np.shape(CT_volume))
print(np.min(CT_volume))
print(np.max(CT_volume))


# Print out some information about your sorted slices
print(f"Number of slices: {len(sorted_images)}")
print(f"First slice instance number: {sorted_images[0].InstanceNumber}")
print(f"Last slice instance number: {sorted_images[-1].InstanceNumber}")
