'''
MIT License

Copyright (c) 2023 Michael Douglass

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''

bl_info = {
    "name" : "MedBlend",
    "author" : "Michael Douglass", 
    "description" : "A Medical image visulisation tool for Blender",
    "blender" : (3, 5, 0),
    "version" : (0, 0, 2),
    "location" : "Australia",
    "warning" : "",
    "doc_url": "https://github.com/drmichaeldouglass/MedBlend", 
    "tracker_url": "", 
    "category" : "3D View" 
}


import bpy
import bpy.utils.previews
from bpy_extras.io_utils import ImportHelper, ExportHelper
import pyopenvdb as openvdb
import numpy as np

import os
from pathlib import Path
import subprocess
import sys
import site


#Custom Packages
from .proton import is_proton_plan
from .node_groups import apply_dose_shader, apply_image_shader, add_CT_to_volume_geo_nodes, add_proton_geo_nodes

try:
    import pydicom
except:
    print('pydicom not installed')

#from bpy.props import StringProperty, BoolProperty, EnumProperty

def verify_user_sitepackages(mda_path):
    usersitepackagespath = site.getusersitepackages()

    if os.path.exists(usersitepackagespath) and usersitepackagespath not in sys.path:
        sys.path.append(usersitepackagespath)
    if os.path.exists(mda_path) and mda_path not in sys.path:
        sys.path.append(mda_path)


    
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

def install_python_modules():

    import subprocess
    import platform

    def isWindows():
        return os.name == 'nt'

    def isMacOS():
        return os.name == 'posix' and platform.system() == "Darwin"

    def isLinux():
        return os.name == 'posix' and platform.system() == "Linux"

    def python_exec():
        import sys
        if isWindows():
            return os.path.join(sys.prefix, 'bin', 'python.exe')
        elif isMacOS():
            try:
                # 2.92 and older
                path = bpy.app.binary_path_python
            except AttributeError:
                # 2.93 and later
                import sys
                path = sys.executable
            return os.path.abspath(path)
        elif isLinux():
            return os.path.join(sys.prefix, 'sys.prefix/bin', 'python')
        else:
            print("sorry, still not implemented for ", os.name, " - ", platform.system)

    def installModule(packageName):
        try:
            subprocess.call([python_exe, "import ", packageName])
        except:
            python_exe = python_exec()
           # upgrade pip
            subprocess.call([python_exe, "-m", "ensurepip"])
            subprocess.call([python_exe, "-m", "pip", "install", "--upgrade", "pip"])
           # install required packages
            subprocess.call([python_exe, "-m", "pip", "install", packageName])
    installModule('pydicom')
    installModule('platipy')
    
    #credit to luckychris https://github.com/luckychris
    return 1  
#This code adapted from https://github.com/simonbroggi/blender_spreadsheet_import
def add_data_fields(mesh, data_fields):
    # add custom data
    for data_field in data_fields:
        mesh.attributes.new(name=data_field if data_field else "empty_key_string", type='FLOAT', domain='POINT')

def create_object(mesh, name):
    # Create new object
    for ob in bpy.context.selected_objects:
        ob.select_set(False)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    return obj

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
  # Create an empty list to store the images
  images = []
  # Loop through all files in the folder
  for filename in os.listdir(folder):
    # Check if the file is a DICOM file
    if filename.endswith(".dcm"):
      # Read the file using pydicom
      image = pydicom.dcmread(os.path.join(folder, filename))
      if check_dicom_image_type(image):
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
      print(slice_spacing)
  dicom_3d_array = np.asarray(dicom_3d_array)   
  dicom_3d_array = np.flipud(dicom_3d_array)
  return dicom_3d_array, spacing, slice_position, slice_spacing, image_origin

def rescale_DICOM_image(array):
    # Get the minimum and maximum values of the array
    min_value = np.min(array)
    max_value = np.max(array)

    # Subtract the minimum and divide by the range
    scaled_array = (array - min_value) / (max_value - min_value)

    # Return the scaled array
    return scaled_array


addon_keymaps = {}
_icons = None
class SNA_PT_MEDBLEND_70A7C(bpy.types.Panel):
    bl_label = 'MedBlend'
    bl_idname = 'SNA_PT_MEDBLEND_70A7C'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_context = ''
    bl_category = 'Medical'
    bl_order = 0
    bl_ui_units_x=0

    @classmethod
    def poll(cls, context):
        return not (False)

    def draw_header(self, context):
        layout = self.layout

    def draw(self, context):
        layout = self.layout
        try:
            import pydicom
            layout.label(text='Images', icon_value=125)
            op = layout.operator('sna.load_ct_fc7b9', text='Load DICOM Images', icon_value=0, emboss=True, depress=False)
            layout.label(text='Dose', icon_value=851)
            op = layout.operator('sna.load_dose_7629f', text='Load DICOM Dose', icon_value=0, emboss=True, depress=False)
            layout.label(text='Structures', icon_value=304)
            op = layout.operator('sna.load_structures_5ebc9', text='Load DICOM Structures', icon_value=0, emboss=True, depress=False)
            layout.label(text='Proton Spots', icon_value=653)
            op = layout.operator('sna.load_proton_1dbc6', text='Load Proton Plan', icon_value=0, emboss=True, depress=False)

        except ModuleNotFoundError:
            layout.label(text='Install Python Dependancies', icon_value=0)
            op = layout.operator('sna.install_python_dependancies', text='Install Dependancies', icon_value=0, emboss=True, depress=False)

            print("module 'pydicom' is not installed")



class SNA_OT_Load_Ct_Fc7B9(bpy.types.Operator, ImportHelper):
    bl_idname = "sna.load_ct_fc7b9"
    bl_label = "Load CT"
    bl_description = "Load a CT Dataset"
    bl_options = {"REGISTER", "UNDO"}
    filter_glob: bpy.props.StringProperty( default='*.dcm', options={'HIDDEN'} )

    @classmethod
    def poll(cls, context):
        if bpy.app.version >= (3, 0, 0) and True:
            cls.poll_message_set('')
        return not False

    def execute(self, context):
        file_name_CT = self.filepath
        print('The name of the CT is ' + str(file_name_CT))

        try:
            import pydicom
        except:
            print('pydicom not installed')

        selected_file = pydicom.dcmread(file_name_CT)
        if check_dicom_image_type(selected_file):
        
            series_uid = selected_file.SeriesInstanceUID
            
            dir_path = Path(file_name_CT)
            dir_path = dir_path.parents[0]
            
            
            # Load all DICOM CT images from your folder using load_dicom_images function
            images = load_dicom_images(dir_path)
            # Filter out only those DICOM CT images that have your specified series UID using filter_by_series_uid function
            filtered_images = filter_by_series_uid(images, series_uid)
            
            # Sort those filtered DICOM CT slices by their instance number using sort_by_instance_number function
            sorted_images = sort_by_instance_number(filtered_images)
            CT_volume, spacing, slice_position, slice_spacing, image_origin = extract_dicom_data(sorted_images)
    

            #CT_volume= np.transpose(CT_volume, axes=(2,1,0))
            #CT_volume = rescale_DICOM_image(CT_volume)
            origin = [image_origin[2], image_origin[1], image_origin[0]]#[int(len(sorted_images)/2)]
            origin = np.asarray(origin)
            volume_dim = np.shape(CT_volume)
            
            # Print out some information about your sorted slices
            print(f"Number of slices: {len(sorted_images)}")
            print(f"First slice instance number: {sorted_images[0].InstanceNumber}")
            print(f"Last slice instance number: {sorted_images[-1].InstanceNumber}")
            
            
            # Create an OpenVDB volume from the pixel data
            grid = openvdb.FloatGrid()
            
            #Copies image volume from numpy to VDB grid
            grid.copyFromArray(CT_volume.astype(float))
            #print(slice_spacing)
            #Scales the grid to slice thickness and pixel size using modified identity transformation matrix. NB. Blender is Z up coordinate system
            grid.transform = openvdb.createLinearTransform([[slice_spacing/1000, 0, 0, 0], [0, spacing[0]/1000, 0, 0], [0,0,spacing[1]/1000,0], [0,0,0,1]])
            #grid.transform.translate = ((origin[0],origin[1],origin[2]))
            
            #Sets the grid class to FOG_VOLUME
            grid.gridClass = openvdb.GridClass.FOG_VOLUME
            
            #Blender needs grid name to be "Density"
            grid.name='density'
            
            #Writes CT volume to a vdb file but perhaps this could be done internally in the future
            openvdb.write(str(dir_path.joinpath("CT.vdb")),grid)
            
            # Add the volume to the scene
            bpy.ops.object.volume_import(filepath=str(dir_path.joinpath("CT.vdb")), files=[])
            bpy.context.active_object.location = origin/1000
            

            #DICOM_object = easybpy.get_selected_object()
            #images_loaded = True
        else:
           print('No DICOM images loaded')
        apply_image_shader()
        return {"FINISHED"}


class SNA_OT_Load_Proton_1Dbc6(bpy.types.Operator, ImportHelper):
    bl_idname = "sna.load_proton_1dbc6"
    bl_label = "Load Proton"
    bl_description = "Load Proton Spots and Weights"
    bl_options = {"REGISTER", "UNDO"}
    filter_glob: bpy.props.StringProperty( default='*.dcm', options={'HIDDEN'} )

    @classmethod
    def poll(cls, context):
        if bpy.app.version >= (3, 0, 0) and True:
            cls.poll_message_set('')
        return not False

    def execute(self, context):
        file_name_proton = self.filepath

        try:
            import pydicom
        except:
            print('pydicom not installed')
        
        import math
        pi_value = math.pi
        # Read the DICOM file and get the spot positions and weights 

        dataset = pydicom.dcmread(file_name_proton) 
        
        if is_proton_plan(dataset):
             print('File is proton plan')
        else:
             print('File is not proton plan')
        
        BeamNo = 0
        for beam in dataset.IonBeamSequence:
            control_points = beam.IonControlPointSequence
            num_control_points = len(control_points)
            #frame_index = 1
            #bpy.ops.object.empty_add(type='PLAIN_AXES', align='WORLD', location=(0, 0, 0), scale=(1, 1, 1))
            #empty = bpy.data.objects['Empty']
            spots = []
            x = []
            y = []
            E = []
            spot_weights = []
            for i in range(0, num_control_points, 2): 
                spots_in_energy_layer = len(beam.IonControlPointSequence[i].ScanSpotPositionMap)
                weights = control_points[i].ScanSpotMetersetWeights
                for j in range(0,spots_in_energy_layer,2):
            
                        x.append(control_points[i].ScanSpotPositionMap[j]/1000)
            
                        y.append(control_points[i].ScanSpotPositionMap[j+1]/1000)
            
                        E.append(float(control_points[i].NominalBeamEnergy)/1000)
                        
                        spot_weights.append(weights[int(j/2)])
                        
                        #spots.append((x,y,E))
                        #spot_weights.append((W,0,0))
                        #print(x,y,E)
                        #if weights[int(j/2)]>0:
                            #empty.location = (x,y,E)
                            #empty.keyframe_insert(data_path="location", frame=frame_index)
                            #frame_index=frame_index + 1
                            #bpy.ops.mesh.primitive_uv_sphere_add(location=(x,y,E), radius=weights[int(j/2)]/10)
            #print(spots)
            #print(spot_weights)
            #print(np.shape(spot_weights))
            #print(np.shape(spots))
            gantry_angle = float(beam.IonControlPointSequence[0].GantryAngle)
            iso_center = np.asarray(beam.IonControlPointSequence[0].IsocenterPosition)/1000
            #mesh = bpy.data.meshes.new('ProtonSpots')
            #mesh.from_pydata(spots, [], [])
            #obj = bpy.data.objects.new('ProtonSpots', mesh)
            
            #bpy.context.scene.collection.objects.link(obj)
            #obj.rotation_euler[1] = gantry_angle*pi_value/180
            #obj.location[0] = iso_center[2]
            #obj.location[1] = iso_center[1]
            #obj.location[2] = iso_center[0]
            
            #mesh = bpy.data.meshes.new('ProtonWeights')
            #mesh.from_pydata(spot_weights, [], [])
            #obj = bpy.data.objects.new('ProtonWeights', mesh)
            
            #bpy.context.scene.collection.objects.link(obj)
            mesh = bpy.data.meshes.new(name="proton_spots")
            
            data_fields = ['spot_x', 'spot_y', 'spot_E', 'spot_weight']
            add_data_fields(mesh,data_fields)
    
    
            for row in range(0,np.shape(spot_weights)[0]):
                    
                mesh.vertices.add(1)
                mesh.update() #might be slow, but does it matter?...
                # assign row values to mesh attribute values
                for data_field in data_fields:
                    mesh.attributes['spot_x'].data[row].value = x[row]
                    mesh.attributes['spot_y'].data[row].value = y[row]
                    mesh.attributes['spot_E'].data[row].value = E[row]
                    mesh.attributes['spot_weight'].data[row].value = spot_weights[row]
                mesh.vertices[row].co = (0.01 * row,0.0,0.0) # set vertex x position according to index
            
            mesh.update()
            mesh.validate()
        
                # create object if data was imported
            if (len(mesh.vertices) > 0):
                obj = create_object(mesh, ['proton_spots' + str(BeamNo)][0])
            
            obj.rotation_euler[1] = gantry_angle*pi_value/180
            obj.location[0] = iso_center[0]
            obj.location[1] = iso_center[1]
            obj.location[2] = iso_center[2]
            
            BeamNo = BeamNo + 1
            add_proton_geo_nodes()
            
            
        #print(np.shape(weights))
        return {"FINISHED"}


class SNA_OT_Load_Dose_7629F(bpy.types.Operator, ImportHelper):
    bl_idname = "sna.load_dose_7629f"
    bl_label = "Load Dose"
    bl_description = "Load a DICOM Dose File"
    bl_options = {"REGISTER", "UNDO"}
    filter_glob: bpy.props.StringProperty( default='*.dcm', options={'HIDDEN'} )

    @classmethod
    def poll(cls, context):
        if bpy.app.version >= (3, 0, 0) and True:
            cls.poll_message_set('')
        return not False

    def execute(self, context):
        file_name_dose = self.filepath

        try:
            import pydicom
        except:
            print('pydicom not installed')
        
        #Directory containing DICOM images
        DICOM_dir = file_name_dose
        
        file_path = Path(DICOM_dir)
        root_dir = file_path.parents[0]
        
        # Load the DICOM dataset
        ds = pydicom.read_file(DICOM_dir) 
        if is_dose_file(ds):
        
            referenced_plan_file_UID = ds.ReferencedRTPlanSequence[0].ReferencedSOPInstanceUID
        
            plan_file_name = root_dir.joinpath('RP' + referenced_plan_file_UID + '.dcm')
        
            try:
                #loads matching plan if possible (not used yet)
                ds_plan = pydicom.read_file(plan_file_name)
            except:
                print('No Plan File')
                
        
            #Get the Dose Grid
            pixel_data = ds.pixel_array 
            
            #If the resolution of the dose grid cannot be found, set the resolution to 1 mm
            try:
                dose_resolution = [ds.PixelSpacing[0]/1000, ds.PixelSpacing[1]/1000, ds.SliceThickness/1000] 
            except:
                dose_resolution = [1/1000, 1/1000, 1/1000]   

            #CT origin coordinates (use DICOM coordinates by default, set to zero otherwise)
            try:
                origin = np.asarray(ds.ImagePositionPatient) 
            except:
                origin = (0,0,0)
        

            #Converts list to numpy array
            dose_matrix = np.asarray(pixel_data)
            
            #Normalises the image volume in range 0,1
            #dose_matrix = dose_matrix/np.max(dose_matrix)
            dose_matrix = rescale_DICOM_image(dose_matrix)
            #dose_matrix = dose_matrix.transpose(0, 2, 1)
            # Create an OpenVDB volume from the pixel data
            
            #Creates a grid of Double precision
            grid = openvdb.FloatGrid()
            #Copies image volume from numpy to VDB grid
            grid.copyFromArray(dose_matrix.astype(float))
            print(dose_resolution)
            #Scales the grid to slice thickness and pixel size using modified identity transformation matrix. NB. Blender is Z up coordinate system
            grid.transform = openvdb.createLinearTransform([[dose_resolution[2], 0, 0, 0], [0, dose_resolution[0], 0, 0], [0,0,dose_resolution[1],0], [0,0,0,1]])
            #grid['center'] = (origin[0], origin[1], origin[2])
        
            #Sets the grid class to FOG_VOLUME
            grid.gridClass = openvdb.GridClass.FOG_VOLUME
            #Blender needs grid name to be "Density"
            grid.name='density'
        
            dose_dir = root_dir.joinpath('dose.vdb')
            #Writes CT volume to a vdb file but perhaps this could be done internally in the future
            openvdb.write(str(dose_dir),grid)
        
            # Add the volume to the scene
            bpy.ops.object.volume_import(filepath=str(dose_dir), files=[])
            #DICOM_object = easybpy.get_selected_object()
            # Set the volume's origin to match the DICOM image position
            bpy.context.object.location = (origin[2]/1000,origin[1]/1000,origin[0]/1000)
            dose_loaded = True
        else:
            print('No Dose File Loaded')
        apply_dose_shader()
        
        return {"FINISHED"}


class SNA_OT_Load_Structures_5Ebc9(bpy.types.Operator, ImportHelper):
    bl_idname = "sna.load_structures_5ebc9"
    bl_label = "Load Structures"
    bl_description = "Load a DICOM Structure Set"
    bl_options = {"REGISTER", "UNDO"}
    filter_glob: bpy.props.StringProperty( default='*.dcm', options={'HIDDEN'} )
    @classmethod
    def poll(cls, context):
        if bpy.app.version >= (3, 0, 0) and True:
            cls.poll_message_set('')
        return not False

    def execute(self, context):
        
        from pathlib import Path
        structure_path  = self.filepath

        try:
            import pydicom
            import platipy
            from platipy.dicom.io.rtstruct_to_nifti import read_dicom_image
            from platipy.dicom.io.rtstruct_to_nifti import transform_point_set_from_dicom_struct
        except:
            print('pydicom not installed')

        # Assume structure_file_path is the path to the structure file specified by the user
        structure_file_path = Path(structure_path)
        
        # Get the directory of the structure file
        structure_directory = structure_file_path.parent
        directory_path = structure_directory
        print(structure_path)
        print(directory_path)
        DICOM_IMAGE = read_dicom_image(directory_path)


        dicom_structure = pydicom.dcmread(structure_path)

        struct_masks, struct_names =  transform_point_set_from_dicom_struct(DICOM_IMAGE, dicom_structure, spacing_override=None)

        # Initialize an empty volume for all structure masks
        all_struct_masks = np.zeros_like(struct_masks[0])

        # Assign each mask a unique integer value
        for i, mask in enumerate(struct_masks, start=1):
            all_struct_masks[mask] = i

        #Creates a grid of Double precision
        grid = openvdb.FloatGrid()
        #Copies image volume from numpy to VDB grid
        grid.copyFromArray(all_struct_masks.astype(float))

        #Scales the grid to slice thickness and pixel size using modified identity transformation matrix. NB. Blender is Z up coordinate system
        #grid.transform = openvdb.createLinearTransform([[dose_resolution[2], 0, 0, 0], [0, dose_resolution[0], 0, 0], [0,0,dose_resolution[1],0], [0,0,0,1]])
        #grid['center'] = (origin[0], origin[1], origin[2])
    
        #Sets the grid class to FOG_VOLUME
        grid.gridClass = openvdb.GridClass.FOG_VOLUME
        #Blender needs grid name to be "Density"
        grid.name='density'
    
        struct_dir = structure_directory.joinpath('structs.vdb')
        #Writes CT volume to a vdb file but perhaps this could be done internally in the future
        openvdb.write(str(struct_dir),grid)
    
        # Add the volume to the scene
        bpy.ops.object.volume_import(filepath=str(struct_dir), files=[])
        #DICOM_object = easybpy.get_selected_object()
        # Set the volume's origin to match the DICOM image position
        #bpy.context.object.location = (origin[2]/1000,origin[1]/1000,origin[0]/1000)
        dose_loaded = True
        
        
        print(struct_names)

# Now dicom_files contains the paths to the DICOM structure files
        
        
        # if is_structure_file(dicom_data):
        
        
        #     # Extract the contour data from the structure file 
        #     contours = [] 
        #     structure_name = []
        #     for i,structure in enumerate(dicom_data.ROIContourSequence): 
        #         points = [] 
        #         structure_name.append(dicom_data.StructureSetROISequence[i].ROIName)
        #         for contour in structure.ContourSequence: 
        
                    
        
        #             for i in range(0, len(contour.ContourData), 3): 
        
        #                 x = contour.ContourData[i+2]/1000
        
        #                 y = contour.ContourData[i+1]/1000
        
        #                 z = contour.ContourData[i]/1000
        
        #                 points.append((x, y, z)) 
        
        #         contours.append(points) 
        
        
        #     # Convert the contours into mesh objects 
        #     bpy.ops.object.select_all(action='DESELECT')  
        #     for j,contour in enumerate(contours):  
        
        #         mesh = bpy.data.meshes.new(name="DICOM Structure") 
        
        #         mesh.from_pydata(contour, [], []) 
        
        #         object = bpy.data.objects.new(structure_name[j], mesh)
                
                
        #         bpy.context.collection.objects.link(object)
        #         bpy.data.objects[object.name].select_set(True)
        #         bpy.context.view_layer.objects.active = object
        
        #else:
            #print('No DICOM Structure Loaded')

        return {"FINISHED"}
    
class install_python_dependancies(bpy.types.Operator):
    bl_idname = "sna.install_python_dependancies"
    bl_label = "Load Python Dependancies"
    bl_description = "Loads Python Modules required for MedBlend"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if bpy.app.version >= (3, 0, 0) and True:
            cls.poll_message_set('')
        return not False

    def execute(self, context):
        

        pydicom_install_successful = install_python_modules()

        return {"FINISHED"}

    def invoke(self, context, event):
        return self.execute(context)


def register():
    global _icons
    _icons = bpy.utils.previews.new()
    bpy.utils.register_class(SNA_PT_MEDBLEND_70A7C)
    bpy.utils.register_class(SNA_OT_Load_Ct_Fc7B9)
    bpy.utils.register_class(SNA_OT_Load_Proton_1Dbc6)
    bpy.utils.register_class(SNA_OT_Load_Dose_7629F)
    bpy.utils.register_class(SNA_OT_Load_Structures_5Ebc9)
    bpy.utils.register_class(install_python_dependancies)
    


def unregister():
    global _icons
    bpy.utils.previews.remove(_icons)
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    for km, kmi in addon_keymaps.values():
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
    bpy.utils.unregister_class(SNA_PT_MEDBLEND_70A7C)
    bpy.utils.unregister_class(SNA_OT_Load_Ct_Fc7B9)
    bpy.utils.unregister_class(SNA_OT_Load_Proton_1Dbc6)
    bpy.utils.unregister_class(SNA_OT_Load_Dose_7629F)
    bpy.utils.unregister_class(SNA_OT_Load_Structures_5Ebc9)
    bpy.utils.unregister_class(install_python_dependancies)
    
    
#register()
