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
    "version" : (0, 0, 1),
    "location" : "",
    "warning" : "",
    "doc_url": "https://github.com/drmichaeldouglass/MedBlend", 
    "tracker_url": "https://github.com/drmichaeldouglass/MedBlend", 
    "category" : "3D View" 
}


import bpy
import bpy.utils.previews
import subprocess
import os
from bpy_extras.io_utils import ImportHelper, ExportHelper
from pathlib import Path
import pyopenvdb as openvdb
import pydicom 


addon_keymaps = {}
_icons = None
class SNA_PT_MEDBLEND_70338(bpy.types.Panel):
    bl_label = 'MedBlend'
    bl_idname = 'SNA_PT_MEDBLEND_70338'
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
        import sys
        import site

        def verify_user_sitepackages(mda_path):
            usersitepackagespath = site.getusersitepackages()
            if os.path.exists(usersitepackagespath) and usersitepackagespath not in sys.path:
                sys.path.append(usersitepackagespath)
            if os.path.exists(mda_path) and mda_path not in sys.path:
                sys.path.append(mda_path)
        # path to python.exe
        python_exe = os.path.realpath(sys.executable)
        # upgrade pip
        subprocess.call([python_exe, "-m", "ensurepip"])
        subprocess.call([python_exe, "-m", "pip", "install",
                        "--upgrade", "pip"], timeout=600)
        # install required packages
        subprocess.call([python_exe, "-m", "pip", "install", "pydicom"], timeout=600)

        def verify_user_sitepackages(package_location):
            if os.path.exists(package_location) and package_location not in sys.path:
                sys.path.append(package_location)
        verify_user_sitepackages(site.getusersitepackages())
        try:
            import pydicom
            pydicom_install_successful = True
        except:
            pydicom_install_successful = False
        return {"FINISHED"}

    def invoke(self, context, event):
        return self.execute(context)


class SNA_OT_Load_Dicom_Images_58Ed9(bpy.types.Operator, ImportHelper):
    bl_idname = "sna.load_dicom_images_58ed9"
    bl_label = "Load DICOM Images"
    bl_description = "Loads DICOM CT or MRI"
    bl_options = {"REGISTER", "UNDO"}
    filter_glob: bpy.props.StringProperty( default='**.dcm', options={'HIDDEN'} )
    files: bpy.props.CollectionProperty(name='Filepaths', type=bpy.types.OperatorFileListElement)

    @classmethod
    def poll(cls, context):
        if bpy.app.version >= (3, 0, 0) and True:
            cls.poll_message_set('')
        return not False

    def execute(self, context):
        Dicom_Files = [os.path.join(os.path.dirname(self.filepath), f.name) for f in self.files]
        DICOM_object = None
        import pydicom
        import numpy as np
        import easybpy
        dicom_series_id = []
        dicom_set = []
        dicom_instance_number = []
        slice_position = []
        dir_path = Path(Dicom_Files[0])
        dir_path = dir_path.parents[0]
        for file in Dicom_Files:
            try:
                dicom = pydicom.dcmread(file, force=True)
                #TODO: NEED TO CHECK IF DICOM IS IMAGE TYPE (NOT PLAN, DOSE STRUCTURES)
            except IOError as e:
                print(f"Can't import DICOM file")
            else:
                dicom_set.append(dicom.pixel_array)
                dicom_series_id.append(dicom.SeriesInstanceUID)
                dicom_instance_number.append(dicom.InstanceNumber)
                #Pixel spacing in X,Y direction
                spacing = dicom.PixelSpacing
                #CT origin coordinates
                slice_position.append(dicom.ImagePositionPatient)
                slice_spacing = dicom.SliceThickness
                image_planes = dicom_set/np.max(dicom_set)
        num_series = len(np.unique(dicom_series_id))
        if num_series>1:
            print('Error: More than One CT Series Found in Folder')
        slice_position = np.asarray(slice_position)
        origin = np.mean(slice_position,axis=0)
        dicom_set = np.asarray(dicom_set)
        print(num_series)
        # Create an OpenVDB volume from the pixel data
        #Creates a grid of Double precision
        grid = openvdb.FloatGrid()
        #Copies image volume from numpy to VDB grid
        grid.copyFromArray(image_planes.astype(float))
        #Scales the grid to slice thickness and pixel size using modified identity transformation matrix. NB. Blender is Z up coordinate system
        grid.transform = openvdb.createLinearTransform([[slice_spacing/1000, 0, 0, 0], [0, spacing[0]/1000, 0, 0], [0,0,spacing[1]/1000,0], [0,0,0,1]])
        #Sets the grid class to FOG_VOLUME
        grid.gridClass = openvdb.GridClass.FOG_VOLUME
        #Blender needs grid name to be "Density"
        grid.name='density'
        #Writes CT volume to a vdb file but perhaps this could be done internally in the future
        openvdb.write(str(dir_path.joinpath("CT.vdb")),grid)
        # Add the volume to the scene
        bpy.ops.object.volume_import(filepath=str(dir_path.joinpath("CT.vdb")), files=[])
        DICOM_object = easybpy.get_selected_object()
        # Set the volume's origin to match the DICOM image position
        #print(origin)
        #py.context.object.location = origin/1000
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
        filepath = struct_dir
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
        return {"FINISHED"}


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
        import pydicom
        import numpy as np
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


def register():
    global _icons
    _icons = bpy.utils.previews.new()
    bpy.utils.register_class(SNA_PT_MEDBLEND_70338)
    bpy.utils.register_class(SNA_AddonPreferences_EEDE7)
    bpy.utils.register_class(SNA_OT_Install_Dependancies_7C0E6)
    bpy.utils.register_class(SNA_OT_Load_Dicom_Images_58Ed9)
    bpy.utils.register_class(SNA_OT_Load_Dicom_Structures_Ac122)
    bpy.utils.register_class(SNA_OT_Load_Dicom_Dose_87594)


def unregister():
    global _icons
    bpy.utils.previews.remove(_icons)
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    for km, kmi in addon_keymaps.values():
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
    bpy.utils.unregister_class(SNA_PT_MEDBLEND_70338)
    bpy.utils.unregister_class(SNA_AddonPreferences_EEDE7)
    bpy.utils.unregister_class(SNA_OT_Install_Dependancies_7C0E6)
    bpy.utils.unregister_class(SNA_OT_Load_Dicom_Images_58Ed9)
    bpy.utils.unregister_class(SNA_OT_Load_Dicom_Structures_Ac122)
    bpy.utils.unregister_class(SNA_OT_Load_Dicom_Dose_87594)
