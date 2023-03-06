

# MedBlend 
A Medical Visualisation Add-On for Blender
![ADC6C67E2-F8F9-48CD-AE18-8AAD63B438D5](https://user-images.githubusercontent.com/52724915/222957178-4d39777b-2366-4918-83f7-b82f3fc717f6.png)


> This project is still in development. The code provided here is still being developed and has not been optimised yet

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

Once installed, under the Medical category in the 3D viewport, select MedBlend and then select "Install Python Modules". This will install some additonal python modules to the Blender python installation which are required for MedBlend to function. This process can take up to a few minutes to complete, please be patient.


![Install_2](https://user-images.githubusercontent.com/52724915/220255502-0530ca5d-0d55-4f21-8b74-050b8879abd0.PNG)

## How to use BlenderRT

Once installed, open the 3D viewport and select the MedBlend category from the sidebar. Press N on the keyboard if it is not visible. 
![Install_3](https://user-images.githubusercontent.com/52724915/220255514-08a69a10-a520-4d10-a956-4c79fdacdc95.PNG)

MedBlend currently has 3 Load functions: Load DICOM images, Load DICOM Dose and Load DICOM structures. Each of these functions imports a specific DICOM medical file. 

Load DICOM Images, will allow you to load a DICOM image sequence from a specified folder. When you press the load images button from the menu, a file dialog will appear. Select a single DICOM image from this folder. MedBlend will search through the same directory and load all DICOM images with the same study ID into Blender automatically. These image slices will be imported and converted to a volume object which can be rendered in Blender. Upon sucessfully importing the images, Blender will automatically add a material to this object (in development). This material can be made brighter by increasing the value on the math node in the shader editor window.


Load DICOM Dose will allow you to import radiation therapy DICOM Dose Files from a treatment planning system and display the dose distribution as a volume in Blender. This add-on will automatically create a material for the volume once imported. This material can be made brighter by increasing the value on the math node in the shader editor window.

Finally, Load DICOM structures will import a DICOM structure file from a radiation therapy treatment planning system and import each structure as a separate point cloud. 

Here are some examples showing a CT, structures and dose volumes imported and overlayed. 
![Dose](https://user-images.githubusercontent.com/52724915/220470967-dd2b78f5-c34b-4c70-a5a5-fcea588e37a8.GIF)
![Structure](https://user-images.githubusercontent.com/52724915/220471006-f343c851-915e-4b51-ada2-8164aebb3ae5.GIF)



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


## Support the development of MedBlend via PayPal
![download](https://user-images.githubusercontent.com/52724915/220474865-3edb00ea-9582-450d-9fb1-e6414b4e8db3.png)



## References

