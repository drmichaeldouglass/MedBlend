# MedBlend
A Medical Visualisation Add-On for Blender

## This project is still in development. The code provided here is still being developed and has not been tested or optimised yet.

## Introduction

## Intended Use

This Blender add-on is intended to be used to create visulisations of radiation therapy treatment plans including DICOM images, plans, structures and dose. This can be used to create high quality figures for presentations or publications. 

## Disclaimer

This package is intended for research or educational purposes only and should not be used for clinical applications. By using this add-on you accept that this software is provided without warranty and the author will not be held liable for any damages caused by the use of this software. 

## Requirements
Blender RT utilises the pydicom module and is installed as a dependancy when you enable the add-on in Blender. The add-on also uses the pyopenvdb module which has recently been added to Blender version 3.5. 

## Installation



## How to use BlenderRT





# (In Progress)

### Import CT or MRI Data

BlenderRT allows you to import radiation therapy or diagnostic medical image files (CT or MRI) in their native DICOM format. The images are imported and displayed as a volume object in Blender which allows for efficient and easily customisable rendering. 

### Import Radiation Therapy Dose Volumes

Simmiarly, BlenderRT can also import DICOM dose files and display them in Blender as a volume object. 

### Import Radiation Therapy Structure Files

Stores DICOM structure fils as point cloud and then solidifies the mesh using geometry nodes (also has STL exported WIP)

### Import Radaition Therapy Plan Files

Linac or Proton Spot DICOM plan files
(In Progress)

### Brachytherapy Dwell Points

(In Progress)

## How to Cite

MedBlend: A Medical Visualisation Add-On for Blender, M.Douglass
https://github.com/drmichaeldouglass/MedBlend

## References

