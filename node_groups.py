import bpy
import os


def append_item_from_blend(file_path, item_type, item_name):
    """
    Append an item from a .blend file
    """
    bpy.ops.wm.append(
        directory=file_path + "\\" + item_type + "\\",
        filename=item_name
    )

def apply_DICOM_shader(shader_name):
    current_path = bpy.path.abspath(os.path.dirname(__file__))

    #combine current path with the immediate sub-folder called "assets"
    path = os.path.join(current_path, "assets")
    #sets assets file name to MedBlend_Assets.blend
    assets_file = os.path.join(path, "MedBlend_Assets.blend")

    #checks if there exists a material in the current scene called "Image Material"
    if not shader_name in bpy.data.materials:
        append_item_from_blend(assets_file, "Material", shader_name)
        #Attach the image material shader to thhe currently selected object
        bpy.context.object.data.materials.append(bpy.data.materials[shader_name])
    else:
        bpy.context.object.data.materials.append(bpy.data.materials[shader_name])

    return True

def apply_proton_spots_geo_nodes(node_tree_name = 'Proton_Spots'):
    """
    Adds the proton spots node group to the selected object
    """
    current_path = bpy.path.abspath(os.path.dirname(__file__))    
    #combine current path with the immediate sub-folder called "assets"
    path = os.path.join(current_path, "assets")
    #sets assets file name to MedBlend_Assets.blend
    assets_file = os.path.join(path, "MedBlend_Assets.blend")    
    # Check if the node tree exists in the data
    if node_tree_name not in bpy.data.node_groups:
        # Append the node tree from the blend file
        append_item_from_blend(assets_file, "NodeTree", node_tree_name)
    
    # Get the currently selected object
    obj = bpy.context.active_object
    
    # Check if the object has a geometry nodes modifier
    geomod = obj.modifiers.get("GeometryNodes")
    if not geomod:
        # If not, create one
        geomod = obj.modifiers.new("GeometryNodes", 'NODES')
    
    # Assign the node tree to the modifier
    geomod.node_group = bpy.data.node_groups[node_tree_name]




def add_proton_geo_nodes():
    """
    Adds the proton spots node group to the selected object
    """

    proton_spots = proton_spots_node_group()    
    name = bpy.context.object.name
    obj = bpy.data.objects[name]
    mod = obj.modifiers.new(name = "Proton_Spots", type = 'NODES')
    mod.node_group = proton_spots