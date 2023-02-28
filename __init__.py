# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTIBILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

bl_info = {
    "name" : "MedBlend",
    "author" : "Michael Douglass", 
    "description" : "A Medical Visualisation Add-On for Blender",
    "blender" : (3, 5, 0),
    "version" : (0, 0, 2),
    "location" : "",
    "warning" : "",
    "doc_url": "https://github.com/drmichaeldouglass/MedBlend", 
    "tracker_url": "https://github.com/drmichaeldouglass/MedBlend", 
    "category" : "3D View" 
}


import bpy
import bpy.utils.previews
import os
from bpy_extras.io_utils import ImportHelper, ExportHelper
from pathlib import Path
import pyopenvdb as openvdb
import pydicom 
import numpy as np


addon_keymaps = {}
_icons = None
class SNA_OT_Load_Dicom_Dose_87594(bpy.types.Operator, ImportHelper):
    bl_idname = "sna.load_dicom_dose_87594"
    bl_label = "Load DICOM Dose"
    bl_description = "Loads DICOM Dose"
    bl_options = {"REGISTER", "UNDO"}
    filter_glob: bpy.props.StringProperty( default='**.dcm', options={'HIDDEN'} )

    @classmethod
    def poll(cls, context):
        if bpy.app.version >= (3, 0, 0) and True:
            cls.poll_message_set('')
        return not False

    def execute(self, context):
        dose_dir = self.filepath
        DICOM_object = None
        dose_loaded = None
        import pydicom
        import numpy as np
        import easybpy
        dose_loaded = False

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
        #Directory containing DICOM images
        DICOM_dir = dose_dir
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
            dose_resolution = [ds.PixelSpacing[0]/1000, ds.PixelSpacing[1]/1000, ds.SliceThickness/1000] 
            #CT origin coordinates
            origin = np.asarray(ds.ImagePositionPatient)
            #Converts list to numpy array
            dose_matrix = np.asarray(pixel_data)
            #Normalises the image volume in range 0,1
            dose_matrix = dose_matrix/np.max(dose_matrix)
            # Create an OpenVDB volume from the pixel data
            #Creates a grid of Double precision
            grid = openvdb.FloatGrid()
            #Copies image volume from numpy to VDB grid
            grid.copyFromArray(dose_matrix.astype(float))
            #Scales the grid to slice thickness and pixel size using modified identity transformation matrix. NB. Blender is Z up coordinate system
            grid.transform = openvdb.createLinearTransform([[dose_resolution[2], 0, 0, 0], [0, dose_resolution[0], 0, 0], [0,0,dose_resolution[1],0], [0,0,0,1]])
            grid['center'] = (origin[0], origin[1], origin[2])
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
            dose_loaded = True
        else:
            print('No Dose File Loaded')
        if dose_loaded:
            before_data = list(bpy.data.materials)
            bpy.ops.wm.append(directory=os.path.join(os.path.dirname(__file__), 'assets', 'Assets.blend') + r'\Material', filename='Dose Material', link=False)
            new_data = list(filter(lambda d: not d in before_data, list(bpy.data.materials)))
            appended_AB6CC = None if not new_data else new_data[0]
            material_name = 'Dose Material'
            DICOM_object = DICOM_object
            import easybpy
            #object = easybpy.get_selected_object()
            print(DICOM_object)
            print(DICOM_object.name)
            easybpy.add_material_to_object(DICOM_object.name,material_name)
        return {"FINISHED"}


class SNA_PT_MEDBLEND_F92BE(bpy.types.Panel):
    bl_label = 'MedBlend'
    bl_idname = 'SNA_PT_MEDBLEND_F92BE'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_context = ''
    bl_category = 'MedBlend'
    bl_order = 0
    bl_ui_units_x=0

    @classmethod
    def poll(cls, context):
        return not (False)

    def draw_header(self, context):
        layout = self.layout

    def draw(self, context):
        layout = self.layout
        layout.label(text='DICOM Images', icon_value=200)
        op = layout.operator('sna.load_dicom_images_58ed9', text='Load DICOM Images', icon_value=0, emboss=True, depress=False)
        layout.label(text='Dose', icon_value=851)
        op = layout.operator('sna.load_dicom_dose_87594', text='Load DICOM Dose', icon_value=0, emboss=True, depress=False)
        layout.label(text='Structures', icon_value=387)
        op = layout.operator('sna.load_dicom_structures_ac122', text='Load DICOM Structures', icon_value=0, emboss=True, depress=False)
        layout.label(text='Proton Spots', icon_value=655)
        op = layout.operator('sna.load_proton_spots_0d63c', text='Load Proton Spots and Weights', icon_value=0, emboss=True, depress=False)


class SNA_OT_Load_Dicom_Structures_Ac122(bpy.types.Operator, ImportHelper):
    bl_idname = "sna.load_dicom_structures_ac122"
    bl_label = "Load DICOM Structures"
    bl_description = "Loads DICOM Structures"
    bl_options = {"REGISTER", "UNDO"}
    filter_glob: bpy.props.StringProperty( default='**.dcm', options={'HIDDEN'} )

    @classmethod
    def poll(cls, context):
        if bpy.app.version >= (3, 0, 0) and True:
            cls.poll_message_set('')
        return not False

    def execute(self, context):
        struct_dir = self.filepath

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
        filepath = struct_dir
        dicom_data = pydicom.dcmread(filepath) 
        if is_structure_file(dicom_data):
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
        else:
            print('No DICOM Structure Loaded')
        return {"FINISHED"}


class SNA_OT_Load_Proton_Spots_0D63C(bpy.types.Operator, ImportHelper):
    bl_idname = "sna.load_proton_spots_0d63c"
    bl_label = "Load Proton Spots"
    bl_description = "Load Proton Spots and Weights from RT Ion DICOM"
    bl_options = {"REGISTER", "UNDO"}
    filter_glob: bpy.props.StringProperty( default='**.dcm', options={'HIDDEN'} )

    @classmethod
    def poll(cls, context):
        if bpy.app.version >= (3, 0, 0) and True:
            cls.poll_message_set('')
        return not False

    def execute(self, context):
        proton_plan = self.filepath
        return {"FINISHED"}


class SNA_OT_Load_Dicom_Images_58Ed9(bpy.types.Operator, ImportHelper):
    bl_idname = "sna.load_dicom_images_58ed9"
    bl_label = "Load DICOM Images"
    bl_description = "Loads DICOM CT or MRI"
    bl_options = {"REGISTER", "UNDO"}
    filter_glob: bpy.props.StringProperty( default='**.dcm', options={'HIDDEN'} )

    @classmethod
    def poll(cls, context):
        if bpy.app.version >= (3, 0, 0) and True:
            cls.poll_message_set('')
        return not False

    def execute(self, context):
        dicom_file = self.filepath
        DICOM_object = None
        images_loaded = None
        # Import pydicom library
        from pathlib import Path
        global os
        import easybpy
        images_loaded = False
        # Specify your file path
        file = dicom_file

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
          for i in range(0,len(sorted_images)):
              dicom_3d_array.append(images[i].pixel_array)
              spacing = images[i].PixelSpacing
              slice_position.append(images[i].ImagePositionPatient)
              slice_spacing = images[i].SliceThickness
          dicom_3d_array = np.asarray(dicom_3d_array)    
          return dicom_3d_array, spacing, slice_position, slice_spacing

        def rescale_DICOM_image(array):
            # Get the minimum and maximum values of the array
            min_value = np.min(array)
            max_value = np.max(array)
            # Subtract the minimum and divide by the range
            scaled_array = (array - min_value) / (max_value - min_value)
            # Return the scaled array
            return scaled_array
        selected_file = pydicom.dcmread(file)
        if check_dicom_image_type(selected_file):
            series_uid = selected_file.SeriesInstanceUID
            dir_path = Path(file)
            dir_path = dir_path.parents[0]
            # Load all DICOM CT images from your folder using load_dicom_images function
            images = load_dicom_images(dir_path)
            # Filter out only those DICOM CT images that have your specified series UID using filter_by_series_uid function
            filtered_images = filter_by_series_uid(images, series_uid)
            # Sort those filtered DICOM CT slices by their instance number using sort_by_instance_number function
            sorted_images = sort_by_instance_number(filtered_images)
            CT_volume, spacing, slice_position, slice_spacing = extract_dicom_data(sorted_images)
            CT_volume = rescale_DICOM_image(CT_volume)
            origin = slice_position[int(len(sorted_images)/2)]
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
            #Scales the grid to slice thickness and pixel size using modified identity transformation matrix. NB. Blender is Z up coordinate system
            grid.transform = openvdb.createLinearTransform([[slice_spacing/1000, 0, 0, 0], [0, spacing[0]/1000, 0, 0], [0,0,spacing[1]/1000,0], [0,0,0,1]])
            grid.transform.translate = ((origin[0],origin[1],origin[2]))
            #Sets the grid class to FOG_VOLUME
            grid.gridClass = openvdb.GridClass.FOG_VOLUME
            #Blender needs grid name to be "Density"
            grid.name='density'
            #Writes CT volume to a vdb file but perhaps this could be done internally in the future
            openvdb.write(str(dir_path.joinpath("CT.vdb")),grid)
            # Add the volume to the scene
            bpy.ops.object.volume_import(filepath=str(dir_path.joinpath("CT.vdb")), files=[])
            DICOM_object = easybpy.get_selected_object()
            images_loaded = True
        else:
           print('No DICOM images loaded')
        if images_loaded:
            before_data = list(bpy.data.materials)
            bpy.ops.wm.append(directory=os.path.join(os.path.dirname(__file__), 'assets', 'Assets.blend') + r'\Material', filename='Image Material', link=False)
            new_data = list(filter(lambda d: not d in before_data, list(bpy.data.materials)))
            appended_FDAE9 = None if not new_data else new_data[0]
            material_name = 'Image Material'
            DICOM_object = DICOM_object
            import easybpy
            #object = easybpy.get_selected_object()
            print(DICOM_object)
            print(DICOM_object.name)
            easybpy.add_material_to_object(DICOM_object.name,material_name)
        return {"FINISHED"}


class SNA_AddonPreferences_EEDE7(bpy.types.AddonPreferences):
    bl_idname = 'medblend'

    def draw(self, context):
        if not (False):
            layout = self.layout 
            layout.label(text='Install Dependancies', icon_value=164)
            op = layout.operator('sna.install_dependancies_7c0e6', text='Install Python Modules', icon_value=0, emboss=True, depress=False)


class SNA_OT_Install_Dependancies_7C0E6(bpy.types.Operator):
    bl_idname = "sna.install_dependancies_7c0e6"
    bl_label = "Install Dependancies"
    bl_description = "Install Python Modules"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if bpy.app.version >= (3, 0, 0) and True:
            cls.poll_message_set('')
        return not False

    def execute(self, context):
        return {"FINISHED"}

    def invoke(self, context, event):
        return self.execute(context)


def register():
    global _icons
    _icons = bpy.utils.previews.new()
    bpy.utils.register_class(SNA_OT_Load_Dicom_Dose_87594)
    bpy.utils.register_class(SNA_PT_MEDBLEND_F92BE)
    bpy.utils.register_class(SNA_OT_Load_Dicom_Structures_Ac122)
    bpy.utils.register_class(SNA_OT_Load_Proton_Spots_0D63C)
    bpy.utils.register_class(SNA_OT_Load_Dicom_Images_58Ed9)
    bpy.utils.register_class(SNA_AddonPreferences_EEDE7)
    bpy.utils.register_class(SNA_OT_Install_Dependancies_7C0E6)


def unregister():
    global _icons
    bpy.utils.previews.remove(_icons)
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    for km, kmi in addon_keymaps.values():
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
    bpy.utils.unregister_class(SNA_OT_Load_Dicom_Dose_87594)
    bpy.utils.unregister_class(SNA_PT_MEDBLEND_F92BE)
    bpy.utils.unregister_class(SNA_OT_Load_Dicom_Structures_Ac122)
    bpy.utils.unregister_class(SNA_OT_Load_Proton_Spots_0D63C)
    bpy.utils.unregister_class(SNA_OT_Load_Dicom_Images_58Ed9)
    bpy.utils.unregister_class(SNA_AddonPreferences_EEDE7)
    bpy.utils.unregister_class(SNA_OT_Install_Dependancies_7C0E6)
