import bpy

#A function to add custom data properties to the selected mesh
#This code was adapted from https://github.com/simonbroggi/blender_spreadsheet_import
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


