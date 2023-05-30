import bpy

def dose_material_shader():
    mat = bpy.data.materials.new(name = "Dose Material")
    mat.use_nodes = True
    dose_material = mat.node_tree
	
    #start with a clean node tree
    for node in dose_material.nodes:
        dose_material.nodes.remove(node)
    #initialize dose_material nodes
    #node Math
    math = dose_material.nodes.new("ShaderNodeMath")
    math.operation = 'MULTIPLY'
    #Value_001
    math.inputs[1].default_value = 2.0
    #Value_002
    math.inputs[2].default_value = 0.5
    #node ColorRamp
    colorramp = dose_material.nodes.new("ShaderNodeValToRGB")
    colorramp.color_ramp.color_mode = 'RGB'
    colorramp.color_ramp.hue_interpolation = 'NEAR'
    colorramp.color_ramp.interpolation = 'LINEAR'
    colorramp.color_ramp.elements.remove(colorramp.color_ramp.elements[0])
    colorramp_cre_0 = colorramp.color_ramp.elements[0]
    colorramp_cre_0.position = 0.0
    colorramp_cre_0.alpha = 0.0
    colorramp_cre_0.color = (0.0, 0.0, 0.0, 0.0)
    colorramp_cre_1 = colorramp.color_ramp.elements.new(0.3227274417877197)
    colorramp_cre_1.alpha = 0.5
    colorramp_cre_1.color = (0.0, 0.029376786202192307, 1.0, 0.5)
    colorramp_cre_2 = colorramp.color_ramp.elements.new(0.6818180680274963)
    colorramp_cre_2.alpha = 1.0
    colorramp_cre_2.color = (1.0, 0.7747962474822998, 0.0, 1.0)
    colorramp_cre_3 = colorramp.color_ramp.elements.new(1.0)
    colorramp_cre_3.alpha = 1.0
    colorramp_cre_3.color = (1.0, 0.0041215610690414906, 0.0, 1.0)
    #node Volume Info
    volume_info = dose_material.nodes.new("ShaderNodeVolumeInfo")
    #node ColorRamp.001
    colorramp_001 = dose_material.nodes.new("ShaderNodeValToRGB")
    colorramp_001.color_ramp.color_mode = 'RGB'
    colorramp_001.color_ramp.hue_interpolation = 'NEAR'
    colorramp_001.color_ramp.interpolation = 'LINEAR'
    colorramp_001.color_ramp.elements.remove(colorramp_001.color_ramp.elements[0])
    colorramp_001_cre_0 = colorramp_001.color_ramp.elements[0]
    colorramp_001_cre_0.position = 0.0
    colorramp_001_cre_0.alpha = 0.0
    colorramp_001_cre_0.color = (0.0, 0.0, 0.0, 0.0)
    colorramp_001_cre_1 = colorramp_001.color_ramp.elements.new(1.0)
    colorramp_001_cre_1.alpha = 1.0
    colorramp_001_cre_1.color = (1.0, 1.0, 1.0, 1.0)
    #node Material Output
    material_output = dose_material.nodes.new("ShaderNodeOutputMaterial")
    material_output.target = 'ALL'
    #Displacement
    material_output.inputs[2].default_value = (0.0, 0.0, 0.0)
    #Thickness
    material_output.inputs[3].default_value = 0.0
    #node Principled Volume
    principled_volume = dose_material.nodes.new("ShaderNodeVolumePrincipled")
    #Color
    principled_volume.inputs[0].default_value = (0.5, 0.5, 0.5, 1.0)
    #Color Attribute
    principled_volume.inputs[1].default_value = ""
    #Density
    principled_volume.inputs[2].default_value = 0.0
    #Density Attribute
    principled_volume.inputs[3].default_value = "density"
    #Anisotropy
    principled_volume.inputs[4].default_value = 0.0
    #Absorption Color
    principled_volume.inputs[5].default_value = (0.0, 0.0, 0.0, 1.0)
    #Blackbody Intensity
    principled_volume.inputs[8].default_value = 0.0
    #Blackbody Tint
    principled_volume.inputs[9].default_value = (1.0, 1.0, 1.0, 1.0)
    #Temperature
    principled_volume.inputs[10].default_value = 1000.0
    #Temperature Attribute
    principled_volume.inputs[11].default_value = "temperature"
    #Weight
    principled_volume.inputs[12].default_value = 0.0
    #Set locations
    math.location = (-253.8451385498047, 547.6362915039062)
    colorramp.location = (-583.43896484375, 330.26849365234375)
    volume_info.location = (-822.9508056640625, 436.30157470703125)
    colorramp_001.location = (-581.3194580078125, 565.661865234375)
    material_output.location = (344.9896545410156, 601.4866943359375)
    principled_volume.location = (-74.74122619628906, 568.8428344726562)
    #Set dimensions
    math.width, math.height = 140.0, 100.0
    colorramp.width, colorramp.height = 240.0, 100.0
    volume_info.width, volume_info.height = 140.0, 100.0
    colorramp_001.width, colorramp_001.height = 240.0, 100.0
    material_output.width, material_output.height = 140.0, 100.0
    principled_volume.width, principled_volume.height = 240.0, 100.
    #initialize dose_material links
    #colorramp_001.Color -> math.Value
    dose_material.links.new(colorramp_001.outputs[0], math.inputs[0])
    #volume_info.Density -> colorramp.Fac
    dose_material.links.new(volume_info.outputs[1], colorramp.inputs[0])
    #volume_info.Density -> colorramp_001.Fac
    dose_material.links.new(volume_info.outputs[1], colorramp_001.inputs[0])
    #math.Value -> principled_volume.Emission Strength
    dose_material.links.new(math.outputs[0], principled_volume.inputs[6])
    #colorramp.Color -> principled_volume.Emission Color
    dose_material.links.new(colorramp.outputs[0], principled_volume.inputs[7])
    #principled_volume.Volume -> material_output.Volume
    dose_material.links.new(principled_volume.outputs[0], material_output.inputs[1])

def apply_dose_shader():
    return dose_material_shader()


        
def image_material_shader():

    mat = bpy.data.materials.new(name = "Image Material")
    mat.use_nodes = True
	#initialize image_material node group

    image_material = mat.node_tree
    #start with a clean node tree
    for node in image_material.nodes:
        image_material.nodes.remove(node)
    #initialize image_material nodes
    #node Material Output
    material_output = image_material.nodes.new("ShaderNodeOutputMaterial")
    material_output.target = 'ALL'
    #Displacement
    material_output.inputs[2].default_value = (0.0, 0.0, 0.0)
    #Thickness
    material_output.inputs[3].default_value = 0.0    
    #node Math
    math = image_material.nodes.new("ShaderNodeMath")
    math.operation = 'MULTIPLY'
    #Value_001
    math.inputs[1].default_value = 5.0
    #Value_002
    math.inputs[2].default_value = 0.5    
    #node ColorRamp
    colorramp = image_material.nodes.new("ShaderNodeValToRGB")
    colorramp.color_ramp.color_mode = 'RGB'
    colorramp.color_ramp.hue_interpolation = 'NEAR'
    colorramp.color_ramp.interpolation = 'LINEAR'    
    colorramp.color_ramp.elements.remove(colorramp.color_ramp.elements[0])
    colorramp_cre_0 = colorramp.color_ramp.elements[0]
    colorramp_cre_0.position = 0.0
    colorramp_cre_0.alpha = 0.0
    colorramp_cre_0.color = (0.0, 0.0, 0.0, 0.0)   
    colorramp_cre_1 = colorramp.color_ramp.elements.new(1.0)
    colorramp_cre_1.alpha = 1.0
    colorramp_cre_1.color = (1.0, 1.0, 1.0, 1.0)
    #node Volume Info
    volume_info = image_material.nodes.new("ShaderNodeVolumeInfo")   
    #node Principled Volume
    principled_volume = image_material.nodes.new("ShaderNodeVolumePrincipled")
    #Color
    principled_volume.inputs[0].default_value = (0.5, 0.5, 0.5, 1.0)
    #Color Attribute
    principled_volume.inputs[1].default_value = ""
    #Density
    principled_volume.inputs[2].default_value = 0.0
    #Density Attribute
    principled_volume.inputs[3].default_value = "density"
    #Anisotropy
    principled_volume.inputs[4].default_value = 0.0
    #Absorption Color
    principled_volume.inputs[5].default_value = (0.0, 0.0, 0.0, 1.0)
    #Blackbody Intensity
    principled_volume.inputs[8].default_value = 0.0
    #Blackbody Tint
    principled_volume.inputs[9].default_value = (1.0, 1.0, 1.0, 1.0)
    #Temperature
    principled_volume.inputs[10].default_value = 1000.0
    #Temperature Attribute
    principled_volume.inputs[11].default_value = "temperature"
    #Weight
    principled_volume.inputs[12].default_value = 0.0    
    #Set locations
    material_output.location = (300.0, 300.0)
    math.location = (-290.64935302734375, 185.22756958007812)
    colorramp.location = (-650.9771118164062, 14.403594970703125)
    volume_info.location = (-876.3124389648438, -123.81324768066406)
    principled_volume.location = (-85.48944091796875, 91.50717163085938)   
    #Set dimensions
    material_output.width, material_output.height = 140.0, 100.0
    math.width, math.height = 140.0, 100.0
    colorramp.width, colorramp.height = 240.0, 100.0
    volume_info.width, volume_info.height = 140.0, 100.0
    principled_volume.width, principled_volume.height = 240.0, 100.0    
    #initialize image_material links
    #colorramp.Color -> math.Value
    image_material.links.new(colorramp.outputs[0], math.inputs[0])
    #colorramp.Color -> principled_volume.Emission Color
    image_material.links.new(colorramp.outputs[0], principled_volume.inputs[7])
    #volume_info.Density -> colorramp.Fac
    image_material.links.new(volume_info.outputs[1], colorramp.inputs[0])
    #math.Value -> principled_volume.Emission Strength
    image_material.links.new(math.outputs[0], principled_volume.inputs[6])
    #principled_volume.Volume -> material_output.Volume
    image_material.links.new(principled_volume.outputs[0], material_output.inputs[1])


def apply_image_shader():
    return image_material_shader()


def ct_volume_to_mesh_node_group():
    ct_volume_to_mesh= bpy.data.node_groups.new(type = "GeometryNodeTree", name = "CT Volume to Mesh")
    #initialize ct_volume_to_mesh nodes
    #ct_volume_to_mesh inputs
    #input Geometry
    ct_volume_to_mesh.inputs.new('NodeSocketGeometry', "Geometry")
    ct_volume_to_mesh.inputs[0].attribute_domain = 'POINT'
    #node Group Input
    group_input = ct_volume_to_mesh.nodes.new("NodeGroupInput")
    #node Cube
    cube = ct_volume_to_mesh.nodes.new("GeometryNodeMeshCube")
    #Vertices X
    cube.inputs[1].default_value = 2
    #Vertices Y
    cube.inputs[2].default_value = 2
    #Vertices Z
    cube.inputs[3].default_value = 2
    #node Mesh Boolean
    mesh_boolean = ct_volume_to_mesh.nodes.new("GeometryNodeMeshBoolean")
    mesh_boolean.operation = 'INTERSECT'
    #Self Intersection
    mesh_boolean.inputs[2].default_value = False
    #Hole Tolerant
    mesh_boolean.inputs[3].default_value = False
    #node Vector
    vector = ct_volume_to_mesh.nodes.new("FunctionNodeInputVector")
    vector.vector = (0.49000000953674316, 3.0299997329711914, 0.38999998569488525)
    #node Transform Geometry
    transform_geometry = ct_volume_to_mesh.nodes.new("GeometryNodeTransform")
    #Translation
    transform_geometry.inputs[1].default_value = (0.17000000178813934, -1.119999885559082, 0.35999998450279236)
    #Rotation
    transform_geometry.inputs[2].default_value = (0.0, 0.0, 0.0)
    #Scale
    transform_geometry.inputs[3].default_value = (1.0, 1.0, 1.0)
    #node Set Shade Smooth
    set_shade_smooth = ct_volume_to_mesh.nodes.new("GeometryNodeSetShadeSmooth")
    #Selection
    set_shade_smooth.inputs[1].default_value = True
    #Shade Smooth
    set_shade_smooth.inputs[2].default_value = True
    #node Set Material
    set_material = ct_volume_to_mesh.nodes.new("GeometryNodeSetMaterial")
    #Selection
    set_material.inputs[1].default_value = True
    if "CT Shader" in bpy.data.materials:
        set_material.inputs[2].default_value = bpy.data.materials["CT Shader"]
    #ct_volume_to_mesh outputs
    #output Geometry
    ct_volume_to_mesh.outputs.new('NodeSocketGeometry', "Geometry")
    ct_volume_to_mesh.outputs[0].attribute_domain = 'POINT'
    #node Group Output
    group_output = ct_volume_to_mesh.nodes.new("NodeGroupOutput")
    #node Realize Instances
    realize_instances = ct_volume_to_mesh.nodes.new("GeometryNodeRealizeInstances")
    #node Volume to Mesh
    volume_to_mesh = ct_volume_to_mesh.nodes.new("GeometryNodeVolumeToMesh")
    volume_to_mesh.resolution_mode = 'VOXEL_SIZE'
    #Voxel Size
    volume_to_mesh.inputs[1].default_value = 0.0010000000474974513
    #Voxel Amount
    volume_to_mesh.inputs[2].default_value = 64.0
    #Threshold
    volume_to_mesh.inputs[3].default_value = 0.2750000059604645
    #Adaptivity
    volume_to_mesh.inputs[4].default_value = 0.0
    #Set locations
    group_input.location = (-458.56182861328125, -7.376960754394531)
    cube.location = (-430.8788146972656, -136.57339477539062)
    mesh_boolean.location = (86.18502807617188, 71.75001525878906)
    vector.location = (-666.7454833984375, -171.49755859375)
    transform_geometry.location = (-170.8945770263672, -139.24826049804688)
    set_shade_smooth.location = (306.3999938964844, 91.71622467041016)
    set_material.location = (526.4000244140625, 75.61817169189453)
    group_output.location = (966.511962890625, 73.02522277832031)
    realize_instances.location = (746.4000244140625, 96.59512329101562)
    volume_to_mesh.location = (-180.77464294433594, 49.2681884765625)
    #Set dimensions
    group_input.width, group_input.height = 140.0, 100.0
    cube.width, cube.height = 140.0, 100.0
    mesh_boolean.width, mesh_boolean.height = 140.0, 100.0
    vector.width, vector.height = 140.0, 100.0
    transform_geometry.width, transform_geometry.height = 140.0, 100.0
    set_shade_smooth.width, set_shade_smooth.height = 140.0, 100.0
    set_material.width, set_material.height = 140.0, 100.0
    group_output.width, group_output.height = 140.0, 100.0
    realize_instances.width, realize_instances.height = 140.0, 100.0
    volume_to_mesh.width, volume_to_mesh.height = 170.0, 100.0
    #initialize ct_volume_to_mesh links
    #group_input.Geometry -> volume_to_mesh.Volume
    ct_volume_to_mesh.links.new(group_input.outputs[0], volume_to_mesh.inputs[0])
    #cube.Mesh -> transform_geometry.Geometry
    ct_volume_to_mesh.links.new(cube.outputs[0], transform_geometry.inputs[0])
    #volume_to_mesh.Mesh -> mesh_boolean.Mesh 1
    ct_volume_to_mesh.links.new(volume_to_mesh.outputs[0], mesh_boolean.inputs[0])
    #transform_geometry.Geometry -> mesh_boolean.Mesh 2
    ct_volume_to_mesh.links.new(transform_geometry.outputs[0], mesh_boolean.inputs[1])
    #volume_to_mesh.Mesh -> mesh_boolean.Mesh 2
    ct_volume_to_mesh.links.new(volume_to_mesh.outputs[0], mesh_boolean.inputs[1])
    #vector.Vector -> cube.Size
    ct_volume_to_mesh.links.new(vector.outputs[0], cube.inputs[0])
    #mesh_boolean.Mesh -> set_shade_smooth.Geometry
    ct_volume_to_mesh.links.new(mesh_boolean.outputs[0], set_shade_smooth.inputs[0])
    #realize_instances.Geometry -> group_output.Geometry
    ct_volume_to_mesh.links.new(realize_instances.outputs[0], group_output.inputs[0])
    #set_shade_smooth.Geometry -> set_material.Geometry
    ct_volume_to_mesh.links.new(set_shade_smooth.outputs[0], set_material.inputs[0])
    #set_material.Geometry -> realize_instances.Geometry
    ct_volume_to_mesh.links.new(set_material.outputs[0], realize_instances.inputs[0])
    return ct_volume_to_mesh



def add_CT_to_volume_geo_nodes():
    ct_volume_to_mesh = ct_volume_to_mesh_node_group()
    name = bpy.context.object.name
    obj = bpy.data.objects[name]
    mod = obj.modifiers.new(name = "CT Volume to Mesh", type = 'NODES')
    mod.node_group = ct_volume_to_mesh





def proton_spots_node_group():
    proton_spots= bpy.data.node_groups.new(type = "GeometryNodeTree", name = "Proton_Spots")

    #initialize proton_spots nodes
    #proton_spots outputs
    #output Geometry
    proton_spots.outputs.new('NodeSocketGeometry', "Geometry")
    proton_spots.outputs[0].attribute_domain = 'POINT'


    #node Group Output
    group_output = proton_spots.nodes.new("NodeGroupOutput")

    #node Combine XYZ
    combine_xyz = proton_spots.nodes.new("ShaderNodeCombineXYZ")

    #node Set Point Radius
    set_point_radius = proton_spots.nodes.new("GeometryNodeSetPointRadius")
    #Selection
    set_point_radius.inputs[1].default_value = True

    #node Math
    math = proton_spots.nodes.new("ShaderNodeMath")
    math.operation = 'MULTIPLY'
    #Value_002
    math.inputs[2].default_value = 0.5

    #node Mesh to Points
    mesh_to_points = proton_spots.nodes.new("GeometryNodeMeshToPoints")
    mesh_to_points.mode = 'VERTICES'
    #Selection
    mesh_to_points.inputs[1].default_value = True
    #Position
    mesh_to_points.inputs[2].default_value = (0.0, 0.0, 0.0)
    #Radius
    mesh_to_points.inputs[3].default_value = 0.05000000074505806

    #node Set Position
    set_position = proton_spots.nodes.new("GeometryNodeSetPosition")
    #Selection
    set_position.inputs[1].default_value = True
    #Offset
    set_position.inputs[3].default_value = (0.0, 0.0, 0.0)

    #node Named Attribute.002
    named_attribute_002 = proton_spots.nodes.new("GeometryNodeInputNamedAttribute")
    named_attribute_002.data_type = 'FLOAT'
    #Name
    named_attribute_002.inputs[0].default_value = "spot_E"

    #node Named Attribute.001
    named_attribute_001 = proton_spots.nodes.new("GeometryNodeInputNamedAttribute")
    named_attribute_001.data_type = 'FLOAT'
    #Name
    named_attribute_001.inputs[0].default_value = "spot_y"

    #node Named Attribute
    named_attribute = proton_spots.nodes.new("GeometryNodeInputNamedAttribute")
    named_attribute.data_type = 'FLOAT'
    #Name
    named_attribute.inputs[0].default_value = "spot_x"

    #node Named Attribute.003
    named_attribute_003 = proton_spots.nodes.new("GeometryNodeInputNamedAttribute")
    named_attribute_003.data_type = 'FLOAT'
    #Name
    named_attribute_003.inputs[0].default_value = "spot_weight"

    #node Set Material
    set_material = proton_spots.nodes.new("GeometryNodeSetMaterial")
    #Selection
    set_material.inputs[1].default_value = True

    #node Reroute
    reroute = proton_spots.nodes.new("NodeReroute")
    #node Reroute.001
    reroute_001 = proton_spots.nodes.new("NodeReroute")
    #node Reroute.002
    reroute_002 = proton_spots.nodes.new("NodeReroute")
    #node Reroute.003
    reroute_003 = proton_spots.nodes.new("NodeReroute")
    #proton_spots inputs
    #input Geometry
    proton_spots.inputs.new('NodeSocketGeometry', "Geometry")
    proton_spots.inputs[0].attribute_domain = 'POINT'

    #input Spot Scale
    proton_spots.inputs.new('NodeSocketFloat', "Spot Scale")
    proton_spots.inputs[1].default_value = 0.004999999888241291
    proton_spots.inputs[1].min_value = 0.0
    proton_spots.inputs[1].max_value = 10000.0
    proton_spots.inputs[1].attribute_domain = 'POINT'

    #input Spot Material
    proton_spots.inputs.new('NodeSocketMaterial', "Spot Material")
    proton_spots.inputs[2].attribute_domain = 'POINT'


    #node Group Input
    group_input = proton_spots.nodes.new("NodeGroupInput")


    #Set locations
    group_output.location = (1118.049072265625, 0.0)
    combine_xyz.location = (-265.6595153808594, -81.25477600097656)
    set_point_radius.location = (678.049072265625, 12.603246688842773)
    math.location = (458.4000244140625, -125.39117431640625)
    mesh_to_points.location = (-53.903465270996094, 134.82223510742188)
    set_position.location = (217.53195190429688, 58.795074462890625)
    named_attribute_002.location = (-495.7137145996094, -390.662109375)
    named_attribute_001.location = (-497.9413146972656, -248.49874877929688)
    named_attribute.location = (-495.3077087402344, -111.37471008300781)
    named_attribute_003.location = (-177.2443084716797, -278.77398681640625)
    set_material.location = (898.3999633789062, 25.0797061920166)
    reroute.location = (-230.80581665039062, 2.1794981956481934)
    reroute_001.location = (-231.6152801513672, 183.9936981201172)
    reroute_002.location = (847.4681396484375, 186.56826782226562)
    reroute_003.location = (852.2462768554688, -74.28929138183594)
    group_input.location = (-490.8133850097656, 82.06087493896484)

    #Set dimensions
    group_output.width, group_output.height = 140.0, 100.0
    combine_xyz.width, combine_xyz.height = 140.0, 100.0
    set_point_radius.width, set_point_radius.height = 140.0, 100.0
    math.width, math.height = 140.0, 100.0
    mesh_to_points.width, mesh_to_points.height = 140.0, 100.0
    set_position.width, set_position.height = 140.0, 100.0
    named_attribute_002.width, named_attribute_002.height = 140.0, 100.0
    named_attribute_001.width, named_attribute_001.height = 140.0, 100.0
    named_attribute.width, named_attribute.height = 140.0, 100.0
    named_attribute_003.width, named_attribute_003.height = 255.61465454101562, 100.0
    set_material.width, set_material.height = 140.0, 100.0
    reroute.width, reroute.height = 16.0, 100.0
    reroute_001.width, reroute_001.height = 16.0, 100.0
    reroute_002.width, reroute_002.height = 16.0, 100.0
    reroute_003.width, reroute_003.height = 16.0, 100.0
    group_input.width, group_input.height = 140.0, 100.0

    #initialize proton_spots links
    #set_material.Geometry -> group_output.Geometry
    proton_spots.links.new(set_material.outputs[0], group_output.inputs[0])
    #mesh_to_points.Points -> set_position.Geometry
    proton_spots.links.new(mesh_to_points.outputs[0], set_position.inputs[0])
    #named_attribute.Attribute -> combine_xyz.X
    proton_spots.links.new(named_attribute.outputs[1], combine_xyz.inputs[0])
    #named_attribute_001.Attribute -> combine_xyz.Y
    proton_spots.links.new(named_attribute_001.outputs[1], combine_xyz.inputs[1])
    #named_attribute_002.Attribute -> combine_xyz.Z
    proton_spots.links.new(named_attribute_002.outputs[1], combine_xyz.inputs[2])
    #combine_xyz.Vector -> set_position.Position
    proton_spots.links.new(combine_xyz.outputs[0], set_position.inputs[2])
    #set_position.Geometry -> set_point_radius.Points
    proton_spots.links.new(set_position.outputs[0], set_point_radius.inputs[0])
    #group_input.Geometry -> mesh_to_points.Mesh
    proton_spots.links.new(group_input.outputs[0], mesh_to_points.inputs[0])
    #math.Value -> set_point_radius.Radius
    proton_spots.links.new(math.outputs[0], set_point_radius.inputs[2])
    #named_attribute_003.Attribute -> math.Value
    proton_spots.links.new(named_attribute_003.outputs[1], math.inputs[0])
    #group_input.Spot Scale -> math.Value
    proton_spots.links.new(group_input.outputs[1], math.inputs[1])
    #set_point_radius.Points -> set_material.Geometry
    proton_spots.links.new(set_point_radius.outputs[0], set_material.inputs[0])
    #reroute_003.Output -> set_material.Material
    proton_spots.links.new(reroute_003.outputs[0], set_material.inputs[2])
    #group_input.Spot Material -> reroute.Input
    proton_spots.links.new(group_input.outputs[2], reroute.inputs[0])
    #reroute.Output -> reroute_001.Input
    proton_spots.links.new(reroute.outputs[0], reroute_001.inputs[0])
    #reroute_001.Output -> reroute_002.Input
    proton_spots.links.new(reroute_001.outputs[0], reroute_002.inputs[0])
    #reroute_002.Output -> reroute_003.Input
    proton_spots.links.new(reroute_002.outputs[0], reroute_003.inputs[0])
    return proton_spots

def add_proton_geo_nodes():
    proton_spots = proton_spots_node_group()    
    name = bpy.context.object.name
    obj = bpy.data.objects[name]
    mod = obj.modifiers.new(name = "Proton_Spots", type = 'NODES')
    mod.node_group = proton_spots