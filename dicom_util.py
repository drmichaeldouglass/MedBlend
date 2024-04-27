# dicom_utilities.py

import os

import numpy as np

try:

    import pydicom

except ImportError:
    
        print("pydicom is not installed. Please install it using the command 'pip install pydicom'")
    
        pydicom = None

    
#Checks if the DICOM file is a RTDose file.
def is_dose_file(ds):
    """
    Checks if the DICOM file at the given path is of type dose.
    Returns True if it is, False otherwise.
    """
    try:
        if ds.Modality == 'RTDOSE':
            return True
        else:
            return False
    except:
        return False
    
#Checks if the DICOM file is a RTStructure file.
def is_structure_file(ds):
    """
    Checks if the DICOM file at the given path is of type structure.
    Returns True if it is, False otherwise.
    """
    try:
        if ds.Modality == 'RTSTRUCT':
            return True
        else:
            return False
    except:
        return False
    

#Checks if the DICOM file is a CT or MRI image
def check_dicom_image_type(ds):
    """
    Check if a DICOM file is a CT or MRI image
    :param dicom_file_path: path to the DICOM file
    :return: 'CT' if the file is a CT image, 'MRI' if the file is an MRI image, and 'Unknown' if the file is neither CT nor MRI
    """
    try:

        if ds.Modality == 'CT':
            return 1
        elif ds.Modality == 'MR':
            return 1
        else:
            return 0

    except Exception as e:
        print(f"Error: {e}")
        return 'Unknown'

# Define a function to load DICOM images from a folder
def load_dicom_images(folder):
    """
    Load DICOM images from a folder and return a list of the images
    :param folder: path to the folder containing the DICOM images
    :return: list of DICOM images
    """
    import pydicom
    print('imported pydicom')
    # Create an empty list to store the images
    images = []
    # Loop through all files in the folder
    for filename in os.listdir(folder):
        # Check if the file is a DICOM file
        if filename.endswith(".dcm"):
            # Read the file using pydicom
            image = pydicom.dcmread(os.path.join(folder, filename))
            if image and check_dicom_image_type(image):
                # Append the image to the list
                images.append(image)
    # Return the list of images
    return images
    

def rescale_DICOM_image(array):
    """
    Rescale the pixel values of a DICOM image to the range [0, 1]
    :param array: 2D or 3D array of pixel values
    :return: 2D or 3D array of rescaled pixel values
    """

    # Get the minimum and maximum values of the array
    min_value = np.min(array)
    max_value = np.max(array)

    # Subtract the minimum and divide by the range
    scaled_array = (array - min_value) / (max_value - min_value)

    # Return the scaled array
    return scaled_array


# Define a function to sort DICOM images by instance number
def sort_by_instance_number(images):
    """
    Sort the list of images by their instance number attribute using lambda function
    :param images: list of DICOM images
    :return: sorted list of DICOM images
    """
    # Sort the list of images by their instance number attribute
    sorted_images = sorted(images, key=lambda x: x.InstanceNumber)
    # Return the sorted list of images
    return sorted_images


def extract_dicom_data(images):

    dicom_3d_array = []
    spacing = []
    slice_position = []
    slice_spacing = []
    for i in range(0,len(images)):
        #dicom_3d_array.append(np.transpose(np.flipud(images[i].pixel_array)))
        dicom_3d_array.append(images[i].pixel_array)
        spacing = images[i].PixelSpacing
        slice_position.append(images[i].ImagePositionPatient)
        slice_spacing = images[i].SliceThickness
        image_origin = images[i].ImagePositionPatient
        image_orientation = images[i].ImageOrientationPatient
        image_columns = images[i].Columns
        print(slice_spacing)
    dicom_3d_array = np.asarray(dicom_3d_array)   
    dicom_3d_array = np.flipud(dicom_3d_array)
    return dicom_3d_array, images[0].PixelSpacing, slice_position, images[0].SliceThickness, images[0].ImagePositionPatient, images[0].ImageOrientationPatient, images[0].Columns


def filter_by_series_uid(images, series_uid):
    """
    Filter a list of DICOM images by their series instance UID
    :param images: list of DICOM images
    :param series_uid: series instance UID to filter by
    :return: filtered list of DICOM images
    """
    
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



