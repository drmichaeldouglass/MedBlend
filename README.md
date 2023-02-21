# MedBlend
A Medical Visualisation Add-On for Blender
### (This project is still in development. The code provided here is still being developed and has not been optimised yet)

## Introduction

## Intended Use

This Blender add-on is intended to be used to create visulisations of radiation therapy treatment plans including DICOM images, plans, structures and dose. This can be used to create high quality figures for presentations or publications. 

## Disclaimer

This package is intended for research or educational purposes only and should not be used for clinical applications. By using this add-on you accept that this software is provided without warranty and the author will not be held liable for any damages caused by the use of this software. 

## Requirements
Blender RT utilises the pydicom module and is installed as a dependancy when you enable the add-on in Blender. The add-on also uses the pyopenvdb module which has recently been added to Blender version 3.5. 

## Installation

### Download MedBlend

To download MedBlend, click the following link and select the latest release.
https://github.com/drmichaeldouglass/MedBlend/tags

Download the add-on installation file which will be of the form: "medblend_0.0.1.zip", for MedBlend version 0.0.1 for example. 

### Install MedBlend

Open Blender 3.5 and from the Edit-->Preferences menu. Select "Add-ons". Then press install and find the medblend_0.0.1.zip file in the file explorer.

![Install_1](https://user-images.githubusercontent.com/52724915/220251356-2493eb54-77b3-43de-9880-fcdd381c3b20.PNG)

Once installed, under the preferences for this add-on, select "Install Python Modules". This will install some additonal python modules to the Blender python installation which are required for MedBlend to function. This process can take up to a few minutes to complete, please be patient.


![Install_2](https://user-images.githubusercontent.com/52724915/220255502-0530ca5d-0d55-4f21-8b74-050b8879abd0.PNG)

## How to use BlenderRT

Once installed, open the 3D viewport and select the MedBlend category from the sidebar. Press N on the keyboard if it is not visible. 
![Install_3](https://user-images.githubusercontent.com/52724915/220255514-08a69a10-a520-4d10-a956-4c79fdacdc95.PNG)

MedBlend currently has 3 Load functions: Load DICOM images, Load DICOM Dose and Load DICOM structures. Each of these functions imports a specific DICOM medical file. 

Load DICOM Images, will allow you to select multiple DICOM image slices from a specified folder. These image slices will be imported and converted to a volume object which can be rendered in Blender. Upon sucessfully importing the images, Blender will automatically add a material to this object. This material can be made brighter by increasing the value on the math node in the shader editor window.


Load DICOM Dose will allow you to import radiation therapy DICOM Dose Files from a treatment planning system and display the dose distribution as a volume in Blender. This add-on will automatically create a material for the volume once imported. This material can be made brighter by increasing the value on the math node in the shader editor window.

Finally, Load DICOM structures will import a DICOM structure file from a radiation therapy treatment planning system and import each structure as a separate point cloud. 

## Known Issues
- Not tested on MRI, SPECT, PET or other imaging modalities.
- CT, Dose and Structure locations are not co-registered yet (user needs to manually align them at the moment).

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

## References

