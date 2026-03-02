![MedBlend Github](https://github.com/drmichaeldouglass/MedBlend/assets/52724915/89374481-2c19-4142-9724-446e2286ad9a)

# MedBlend 
A Medical Visualisation Add-On for Blender

> This project is still in development. The code provided here is still being developed and has not been optimised yet

![GitHub all releases](https://img.shields.io/github/downloads/drmichaeldouglass/MedBlend/total?style=social)
![GitHub Repo stars](https://img.shields.io/github/stars/drmichaeldouglass/medblend?style=social)
![GitHub User's stars](https://img.shields.io/github/stars/drmichaeldouglass?label=User%20Stars&style=social)


## Introduction

## Intended Use

This Blender add-on is intended to be used to create visulisations of radiation therapy treatment plans including DICOM images, plans, structures and dose. This can be used to create high quality figures for presentations or publications. 

## Disclaimer

This package is intended for research or educational purposes only and should not be used for clinical applications. By using this add-on you accept that this software is provided without warranty and the author will not be held liable for any damages caused by the use of this software. 

## Requirements
MedBlend requires only the pydicom module, which is installed when you enable the add-on in Blender.

Optional modules are needed for some features:
- numpy (CT, dose, and RT structure conversion)
- pyopenvdb (volume import/export; bundled with Blender 5.0+)

## Installation

### Download MedBlend

To download MedBlend, click the following link and select the latest release.
https://github.com/drmichaeldouglass/MedBlend/tags

Download the add-on installation file which will be of the form: "medblend_0.0.1.zip", for MedBlend version 0.0.1 for example. 

### Install MedBlend (If you have administrator rights to your PC)

If you have local administrator rights to run Blender then use these instructions otherwise, use the instructions in the next section.

Open Blender 5.0 or newer, ensuring to run Blender using administrator privileges when required by your OS policy. From the Edit-->Preferences menu, select "Add-ons", then press Install and select the MedBlend zip file.

![Install_1](https://user-images.githubusercontent.com/52724915/220251356-2493eb54-77b3-43de-9880-fcdd381c3b20.PNG)
![add_on_install](https://user-images.githubusercontent.com/52724915/226311722-c2d06900-b1db-4056-a5ce-64bf2ca490ba.png)

Once installed, under the Medical category in the 3D viewport, select MedBlend and then select "Install Python Modules". This will install some additonal python modules to the Blender python installation which are required for MedBlend to function. This process can take up to a few minutes to complete, please be patient. Once complete, you may have to restart Blender for the new DICOM options to appear.



![install_python](https://user-images.githubusercontent.com/52724915/226311500-9c8de27c-7180-4ca8-acc9-c29478600b96.png)


### Install MedBlend (If you don't have administrator rights to your PC)

If you don't have administrator rights to your PC, you can use MedBlend by installing the add-on to a portable version of Blender. The portable versions of Blender can be identified by the ".zip" type Blender downloads (shown in the figure below).

Releases of Blender can be downloaded from here: https://www.blender.org/download/

Experimental builds can be downloaded here: https://builder.blender.org/download/daily/

![blender_portable](https://user-images.githubusercontent.com/52724915/226309978-c3b34cac-d97f-49c6-9ea9-76a086e76fb7.png)


Ensure that the version of Blender that you download is 5.0 or later. Once downloaded, unzip the file and look for Blender.exe. This version of Blender can be run locally without installation or saved to a USB drive. 

Blender, by default, installs add-ons to a versioned scripts folder under your user profile (for example: C:\Users\(username)\AppData\Roaming\Blender Foundation\Blender\5.0\scripts\addons). If you do not have administrator rights to your PC, you may need to manually install the add-on to the portable version of Blender you downloaded.

Start by un-zipping the MedBlend add-on zip. Once un-zipped, you should have a folder called "medblend" that contains `__init__.py`. Copy the "medblend" folder into your portable Blender add-ons path (for example: "D:\Blender5.0\5.0\scripts\addons\medblend\__init__.py"). Your Blender path may differ.

Load Blender portable by running Blender.exe. When you select Edit-->Preferences and Add-Ons, you should find that MedBlend is already installed. 

![add_on_install](https://user-images.githubusercontent.com/52724915/226311899-a479f86d-c611-4940-a706-d8814def3533.png)

Once installed, under the Medical category in the 3D viewport, select MedBlend and then select "Install Dependancies". This will install some additonal python modules to the Blender python installation which are required for MedBlend to function. This process can take up to a few minutes to complete, please be patient.

![install_python](https://user-images.githubusercontent.com/52724915/226311909-2a25058e-d473-4225-917f-693ff46e39d7.png)

MedBlend bundles wheels from the add-on `wheels/` directory. Include compatible wheels for required modules such as `pydicom` (and `numpy` if your Blender Python environment does not already provide it).

## How to use MedBlend

Once installed, open the 3D viewport and select the Medical category from the sidebar. Press N on the keyboard if it is not visible. 

![medBlendFunctions](https://user-images.githubusercontent.com/52724915/226313830-c5dbd57b-5199-40f0-befd-4f3da1883e45.png)


MedBlend currently has 4 main functions: Load DICOM images, Load DICOM Dose, Load DICOM structures and Load Proton Plan. Each of these functions imports a specific DICOM medical file. 

-Load DICOM Images, will allow you to load a DICOM image sequence from a specified folder. When you press the load images button, a file dialog will appear. Select a single DICOM image from this folder. MedBlend will search through the same directory and load all DICOM images with the same study ID into Blender automatically. These image slices will be imported and converted to a volume object which can be rendered in Blender. 

-Load DICOM Dose will allow you to import radiation therapy DICOM Dose Files from a treatment planning system and display the dose distribution as a volume in Blender. 

-Load DICOM structures will import a DICOM structure file from a radiation therapy treatment planning system and import each structure as a separate point cloud. 

-Load Proton Plan will import a DICOM RT Ion proton therapy plan file and extract the proton spot positions and weights and display them as spheres with a radius proportional to the relative spot weight. 

## How to add Materials to the CT and dose volumes

Some default materials for CT, MRI and Dose volumes have been included in this add-on. When a DICOM image or DICOM dose volume is imported, a default material is automatically created. Select the materials menu from the menu on the right side, and select either Image Material for CT volumes or Dose Material for dose volumes. 

![materials](https://github.com/drmichaeldouglass/MedBlend/assets/52724915/baf02ebf-5781-4c84-8884-39ff74582adf)

With the CT or dose object selected in the outliner (top right), go to the shader/material menu (red icon in lower right) and select either the Image Material or Dose Material depending on what type of volume you have imported.

To change the material properties, select the Shading tab from the top edge and you should see the Material node setup shown in the bottom panel. MedBlend works with both the Eevee and Cycles render engines but Cycles generally produces better results without too many changes. You can change from Eevee to Cycles from the panel on the right. From the material nodes (shown in panel at the bottom), the brightness of the volume can be changed by increasing the "multiply" value. The pixel threshold can be adjusted by moving the slider points in the colour ramp node. 

![materials3](https://user-images.githubusercontent.com/52724915/226318971-e3f63834-0569-43a0-8828-2ea77c7fe8cd.png)

Generally, DICOM CT is not normalised and pixel values (Hounsfield units) can range from -1000 to > 2000 usually. A value of -10000 generally indicates air density, a value of 0 indicates water density and bone and other high density materials have values >1000. To account for this in the shader material, it may be necessary to add a Map Range node after the volume info node and setting the maximum and miniumum input values to suit your specific dataset. 

![MapRange](https://github.com/drmichaeldouglass/MedBlend/assets/52724915/4905bd84-addd-44c6-ac2a-44de5c9a42dc)

## Converting CT volumes into a mesh

Rather than viewing the DICOM data as a volume, it is possible to convert the CT data into a mesh. This can be performed by apply the volume to mesh modifier in Blender. 

Start by creating a place-holder object. From the add menu, add a cube into the scene. This cube object will hold the volume to mesh modifier. 

![add_cube](https://github.com/drmichaeldouglass/MedBlend/assets/52724915/9f842bce-1a6a-4c7d-8334-1a4c86373e0c)

With the cube selected, go to the modifer menu, select Add Modifier and add a Volume to Mesh modifier.
![volume_to_mesh](https://github.com/drmichaeldouglass/MedBlend/assets/52724915/7f940498-9199-4bc3-b13e-75f76834846a)

From the object property, select the CT volume. Depending on the normalisation of the volume, you will need to adjust the threshold to visulise the data. For most CT data, a threshold value of 100 is a good starting point

![volume_to_mesh_select_CT](https://github.com/drmichaeldouglass/MedBlend/assets/52724915/decbcaab-e009-4f8a-b5a3-eb1d1cec4795)

This is what the mesh should look like with a threshold set to 100. You can apply this modifier from the Volume to Mesh modifier panel to bake the mesh which will allow for manual adjustments.

![CT_Mesh](https://github.com/drmichaeldouglass/MedBlend/assets/52724915/c8b74c1d-baa3-4962-b29e-5eff716fb3f8)

Here are some examples:

A CT scan, structures and dose volumes imported and overlayed. 

![Dose](https://user-images.githubusercontent.com/52724915/220470967-dd2b78f5-c34b-4c70-a5a5-fcea588e37a8.GIF)

DICOM structures for a test prostate radiotherapy plan showing organs at risk such as prostate, urethra, bladder, rectum and the external structure.

![Structure](https://user-images.githubusercontent.com/52724915/220471006-f343c851-915e-4b51-ada2-8164aebb3ae5.GIF)

A test proton therapy plan on a phantom. The CT images, dose distribution and proton spots are shown.

![Proton](https://user-images.githubusercontent.com/52724915/226314672-d9df0645-27b0-4a92-a315-d1a19d69b526.GIF)



## Known Issues
- Not tested on MRI, SPECT, PET or other imaging modalities.
- CT, Dose and Structure locations are not perfectly co-registered yet (user may need to manually align them at the moment).
- After installing the python modules, the DICOM functions sometimes do not appear. This can be fixed by restarting Blender.

Please report any bugs as an issue on this repository

## Future Updates

### Import Radaition Therapy Plan Files

Import radaition therapy DICOM plan files to visulise MLC or proton spot positions in the patient CT

### Import Brachytherapy Dwell Points

Visulise brachytherapy dwell point positions and dwell times

### Treatment simulation with Linac model.


## How to Cite

MedBlend: A Medical Visualisation Add-On for Blender, M.Douglass
https://github.com/drmichaeldouglass/MedBlend

DOI: 10.5281/zenodo.10633327

## References
