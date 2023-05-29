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
MedBlend utilises the pydicom module and is installed as a dependancy when you enable the add-on in Blender. The add-on also uses the pyopenvdb module which has recently been added to Blender version 3.5. 

## Installation

### Download MedBlend

To download MedBlend, click the following link and select the latest release.
https://github.com/drmichaeldouglass/MedBlend/tags

Download the add-on installation file which will be of the form: "medblend_0.0.1.zip", for MedBlend version 0.0.1 for example. 

### Install MedBlend (If you have administrator rights to your PC)

If you have local administrator rights to run Blender then use these instructions otherwise, use the instructions in the next section.

Open Blender 3.5, ensuring to run Blender using administrator privalidges. From the Edit-->Preferences menu. Select "Add-ons". Then press install and find the medblend_0.0.1.zip file in the file explorer.

![Install_1](https://user-images.githubusercontent.com/52724915/220251356-2493eb54-77b3-43de-9880-fcdd381c3b20.PNG)
![add_on_install](https://user-images.githubusercontent.com/52724915/226311722-c2d06900-b1db-4056-a5ce-64bf2ca490ba.png)

Once installed, under the Medical category in the 3D viewport, select MedBlend and then select "Install Python Modules". This will install some additonal python modules to the Blender python installation which are required for MedBlend to function. This process can take up to a few minutes to complete, please be patient. Once complete, you may have to restart Blender for the new DICOM options to appear.



![install_python](https://user-images.githubusercontent.com/52724915/226311500-9c8de27c-7180-4ca8-acc9-c29478600b96.png)


### Install MedBlend (If you don't have administrator rights to your PC)

If you don't have administrator rights to your PC, you can use MedBlend by installing the add-on to a portable version of Blender. The portable versions of Blender can be identified by the ".zip" type Blender downloads (shown in the figure below).

Releases of Blender can be downloaded from here: https://www.blender.org/download/

Experimental builds can be downloaded here: https://builder.blender.org/download/daily/

![blender_portable](https://user-images.githubusercontent.com/52724915/226309978-c3b34cac-d97f-49c6-9ea9-76a086e76fb7.png)


Ensure that the version of Blender that you download is 3.5 or later. Once downloaded, unzip the file and look for the file called Blender.exe. This version of Blender can be run locally without installation or saved to a USB drive. 

Blender, by default will try and install add-ons to the directory: C:\Users\(username)\AppData\Roaming\Blender Foundation\Blender\3.5\scripts\addons. If you do not have administrator rights to your PC, you will not be able to install add-ons to this directory. Instead, you will need to manually install the add-on to the portable version of Blender you have just downloaded.

Start by un-zipping the MedBlend add-on (medblend_0.0.1.zip) for example. Once un-zipped, you should have a folder called "medblend" which contains a file called init.py. Copy the folder "medblend" to the directory "D:\Blender3.5\3.5\scripts\addons" so that the directory structure now looks like "D:\Blender3.5\3.5\scripts\addons\medblend\init.py". Your path to Blender 3.5 might look different, so change accordingly. 

Load up Blender 3.5 portable by running blender.exe. When you select Edit-->Preferences and Add-Ons, you should find that MedBlend is already installed. 

![add_on_install](https://user-images.githubusercontent.com/52724915/226311899-a479f86d-c611-4940-a706-d8814def3533.png)

Once installed, under the Medical category in the 3D viewport, select MedBlend and then select "Install Dependancies". This will install some additonal python modules to the Blender python installation which are required for MedBlend to function. This process can take up to a few minutes to complete, please be patient.

![install_python](https://user-images.githubusercontent.com/52724915/226311909-2a25058e-d473-4225-917f-693ff46e39d7.png)

Installing the python modules should download a module named "pydicom" to the following location "D:\Blender3.5\3.5\python\lib\site-packages". If pydicom is not in this location, MedBlend will not function correctly.

## How to use MedBlend

Once installed, open the 3D viewport and select the Medical category from the sidebar. Press N on the keyboard if it is not visible. 

![medBlendFunctions](https://user-images.githubusercontent.com/52724915/226313830-c5dbd57b-5199-40f0-befd-4f3da1883e45.png)


MedBlend currently has 4 main functions: Load DICOM images, Load DICOM Dose, Load DICOM structures and Load Proton Plan. Each of these functions imports a specific DICOM medical file. 

-Load DICOM Images, will allow you to load a DICOM image sequence from a specified folder. When you press the load images button, a file dialog will appear. Select a single DICOM image from this folder. MedBlend will search through the same directory and load all DICOM images with the same study ID into Blender automatically. These image slices will be imported and converted to a volume object which can be rendered in Blender. 

-Load DICOM Dose will allow you to import radiation therapy DICOM Dose Files from a treatment planning system and display the dose distribution as a volume in Blender. 

-Load DICOM structures will import a DICOM structure file from a radiation therapy treatment planning system and import each structure as a separate point cloud. 

-Load Proton Plan will import a DICOM RT Ion proton therapy plan file and extract the proton spot positions and weights and display them as spheres with a radius proportional to the relative spot weight. 

## How to add Materials to the CT and dose volumes

Some default materials have been included in the github repository in the assets folder and then assets.blend. Download this blender file. In blender, once you have imported your CT or dose volumes, go to the file menu --> append and find the assets.blend file. Go to the materials sub-folder and select Image Material and Dose Material. This will import the default materials so that they become available in Blender. 

With the CT or dose object selected in the outliner (top right), go to the shader/material menu (red icon in lower right) and select either the Image Material or Dose Material depending on what type of volume you have imported.

![materials2](https://user-images.githubusercontent.com/52724915/226318074-58e686b0-bad9-4daf-bdbe-f2dae06c7463.png)

To change the material properties, select the Shading tab from the top edge and you should see the Material node setup shown in the bottom panel. MedBlend works with both the Eevee and Cycles render engines but Cycles generally produces better results without too many changes. You can change from Eevee to Cycles from the panel on the right. From the material nodes (shown in panel at the bottom), the brightness of the volume can be changed by increasing the "multiply" value. The pixel threshold can be adjusted by moving the slider points in the colour ramp node. 

![materials3](https://user-images.githubusercontent.com/52724915/226318971-e3f63834-0569-43a0-8828-2ea77c7fe8cd.png)


Here are some examples:

A CT scan, structures and dose volumes imported and overlayed. 

![Dose](https://user-images.githubusercontent.com/52724915/220470967-dd2b78f5-c34b-4c70-a5a5-fcea588e37a8.GIF)

DICOM structures for a test prostate radiotherapy plan showing organs at risk such as prostate, urethra, bladder, rectum and the external structure.

![Structure](https://user-images.githubusercontent.com/52724915/220471006-f343c851-915e-4b51-ada2-8164aebb3ae5.GIF)

A test proton therapy plan on a phantom. The CT images, dose distribution and proton spots are shown.

![Proton](https://user-images.githubusercontent.com/52724915/226314672-d9df0645-27b0-4a92-a315-d1a19d69b526.GIF)



## Known Issues
- Not tested on MRI, SPECT, PET or other imaging modalities.
- CT, Dose and Structure locations are not co-registered yet (user needs to manually align them at the moment).
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


## Support the development of MedBlend via PayPal
![download](https://user-images.githubusercontent.com/52724915/220474865-3edb00ea-9582-450d-9fb1-e6414b4e8db3.png)



## References

