![MedBlend Github](https://github.com/drmichaeldouglass/MedBlend/assets/52724915/89374481-2c19-4142-9724-446e2286ad9a)

# MedBlend

A medical visualisation extension for Blender.

> MedBlend is under active development and is intended for research, education, and scientific communication.

![GitHub all releases](https://img.shields.io/github/downloads/drmichaeldouglass/MedBlend/total?style=social)
![GitHub Repo stars](https://img.shields.io/github/stars/drmichaeldouglass/medblend?style=social)
![GitHub User's stars](https://img.shields.io/github/stars/drmichaeldouglass?label=User%20Stars&style=social)


## Intended use

MedBlend imports DICOM images, radiotherapy dose, structure sets, and proton plans into Blender to create visualisations for research, education, presentations, and publications.

## Disclaimer

MedBlend is not a medical device and must not be used for diagnosis, treatment planning, treatment delivery, or other clinical decisions. The software is provided without warranty.

## Data handling and privacy

MedBlend processes DICOM files locally and makes no network requests. It reads files selected by the user and writes generated VDB volume files to Blender's temporary directory or a directory selected in the extension preferences.

DICOM data may contain identifying health information. MedBlend does not deliberately copy patient names or patient IDs into Blender, but imported voxel data, ROI and beam names, and technical DICOM identifiers can remain in generated VDB files or the saved `.blend` file. De-identify source data and review exported files before sharing them.

## Requirements

MedBlend requires Blender 5.0 or newer. It is tested against Blender 5.x, including Blender 5.2 LTS.

The extension package includes the `pydicom` wheel declared in `blender_manifest.toml`. Blender installs this dependency into the extension's managed Python environment. NumPy and OpenVDB are supplied by supported Blender builds.

## Installation

### Blender Extensions platform

Once MedBlend has been approved and published:

1. Open `Edit > Preferences > Get Extensions`.
2. Search for `MedBlend`.
3. Select `Install`.

### Install a release package from disk

1. Download the `medblend-<version>.zip` asset from the [latest GitHub release](https://github.com/drmichaeldouglass/MedBlend/releases/latest). Do not use GitHub's automatically generated "Source code" archives.
2. In Blender 5.0 or newer, open `Edit > Preferences > Get Extensions`.
3. Open the menu in the top-right corner and choose `Install from Disk`.
4. Select the downloaded extension package.

Blender installs the bundled dependency automatically. Open the 3D viewport sidebar with `N`, then select the `Medical` tab.

## How to use MedBlend

Once installed, open the 3D viewport and select the Medical category from the sidebar. Press N on the keyboard if it is not visible. 

If Blender cannot write temporary VDB files in its default temp location, open the MedBlend add-on preferences and set a `VDB Temp Directory` that your user account can write to.

> **Note on saving .blend files:** Blender volume objects read their voxel data from the VDB file on disk. By default MedBlend writes VDB files to Blender's session temporary directory, which is deleted when Blender exits - so a saved .blend file will lose its volume data on the next reload. If you plan to save your scene, set a persistent `VDB Temp Directory` in the MedBlend preferences first. Files in that directory are never overwritten or cleaned up automatically (each import writes a new uniquely-named file), so clear it out occasionally.

<img width="393" height="349" alt="Screenshot 2026-03-08 at 9 17 49 pm" src="https://github.com/user-attachments/assets/d000dc5a-3752-46c7-a758-292e3ed7b100" />


MedBlend currently has 4 main functions: Load DICOM images, Load DICOM Dose, Load DICOM structures and Load Proton Plan. Each of these functions imports a specific DICOM medical file. 

- **Load DICOM Images** allows you to load a DICOM image sequence from a specified folder. When you press the load images button, a file dialog will appear. Select a single DICOM image from this folder. MedBlend will search through the same directory and load all DICOM images belonging to the same series (matching SeriesInstanceUID) into Blender automatically. These image slices will be imported and converted to a volume object which can be rendered in Blender. The file dialog also has a `Preset` dropdown, which builds the imported volume's material from one of the [volume rendering presets](#volume-rendering-presets) instead of the default Image Material. 

- **Load DICOM Dose** imports a radiotherapy DICOM dose file and displays the dose distribution as a volume in Blender. 

- **Load DICOM Structures** imports a radiotherapy DICOM structure set. Each ROI is rasterised onto the referenced CT grid and imported as its own volume object, cropped to the bounding box of that structure so a single ROI does not carry the whole CT grid. Each structure gets its own copy of the structure material, tinted with the `ROIDisplayColor` from the planning system, so the ROIs are distinguishable as soon as they are imported. 

- **Load Proton Plan** imports a DICOM RT Ion plan and displays proton spot positions as spheres with radius proportional to relative spot weight. 

## How to add Materials to the CT and dose volumes

Some default materials for CT, MRI and Dose volumes have been included in this add-on. When a DICOM image or DICOM dose volume is imported, a default material is automatically created. Select the materials menu from the menu on the right side, and select either Image Material for CT volumes or Dose Material for dose volumes. 

![materials](https://github.com/drmichaeldouglass/MedBlend/assets/52724915/baf02ebf-5781-4c84-8884-39ff74582adf)

With the CT or dose object selected in the outliner (top right), go to the shader/material menu (red icon in lower right) and select either the Image Material or Dose Material depending on what type of volume you have imported.

To change the material properties, select the Shading tab from the top edge and you should see the Material node setup shown in the bottom panel. MedBlend works with both the Eevee and Cycles render engines but Cycles generally produces better results without too many changes. You can change from Eevee to Cycles from the panel on the right. From the material nodes (shown in panel at the bottom), the brightness of the volume can be changed by increasing the "multiply" value. The pixel threshold can be adjusted by moving the slider points in the colour ramp node. 

![materials3](https://user-images.githubusercontent.com/52724915/226318971-e3f63834-0569-43a0-8828-2ea77c7fe8cd.png)

DICOM CT is stored in Hounsfield units, which typically run from about -1000 (air) through 0 (water) to well beyond 1000 (bone). MedBlend normalises each imported image volume to the range `0 - 1` so it renders correctly without per-dataset shader tweaking, and records the source range on the imported object as the custom properties `medblend_intensity_min` and `medblend_intensity_max` (visible in `Object Properties > Custom Properties`).

To work in Hounsfield units, convert a normalised voxel value back with:

```
HU = value * (medblend_intensity_max - medblend_intensity_min) + medblend_intensity_min
```

A Map Range node after the Volume Info node is the easiest way to isolate a particular HU window - map the normalised `0 - 1` input down to the fraction of the range that your tissue of interest occupies.

Imported dose volumes are *not* normalised: their voxels hold absolute dose, and the maximum value and dose units are recorded on the object as `medblend_dose_max` and `medblend_dose_units`.

![MapRange](https://github.com/drmichaeldouglass/MedBlend/assets/52724915/4905bd84-addd-44c6-ac2a-44de5c9a42dc)

## Volume rendering presets

MedBlend ships the 31 volume rendering presets from [3D Slicer](https://www.slicer.org) - `CT-Bone`, `CT-Lung`, `CT-Cardiac`, `MR-Default`, `MR-T2-Brain`, `uCT-Skull` and the rest - as ready-made Blender volume materials. Each one is Slicer's own colour transfer function and scalar opacity function rebuilt as colour ramps in a Principled Volume shader, so a freshly imported CT or MR looks like the equivalent view in Slicer without hand-tuning a shader.

Apply one either way:

- **At import.** Pick a preset in the `Preset` dropdown of the Load DICOM Images file dialog. Leaving it on `Default Image Material` keeps the previous behaviour.
- **Afterwards.** Select one or more imported volumes, choose a preset under `Image Volume Presets` in the Medical sidebar, and press `Apply Preset`.

Three settings control how the preset lands:

- **Scalar Range** decides how the preset's scalar values map onto your data. Slicer's `CT-` presets are keyed to Hounsfield units, which are calibrated, so on a CT they are read directly against the volume's recorded HU range. Everything else - MR, ultrasound, micro-CT - is stored in per-scan intensities with no fixed meaning, so the preset's authored window is stretched across whatever range the volume occupies. `Auto` picks between the two for you; `Hounsfield Units` and `Fit To Data` force one.
- **Density** is the extinction of a fully opaque voxel, in 1/m. Raise it for a more solid volume, lower it to see further inside. Blender volumes are imported in metres, so this is what converts Slicer's per-sample opacity into something Blender can integrate.
- **Emission** is how brightly the volume glows on its own. The default of `1.0` means a preset reads immediately without adding a light; drop it towards zero to light the volume with scene lights and let the preset's colours act as scattering albedo instead.

Applying the same preset with the same settings reuses one material, so pushing a preset onto several volumes - or re-applying it after an edit - does not fill the file with copies. Different settings get their own material rather than changing one that another volume is already using.

### Editing a preset material

Open the Shading tab with the volume selected and you get a small, editable node tree:

- **Window** (a Map Range node) is the equivalent of Slicer's shift slider. Narrowing `From Min`/`From Max` squeezes the whole preset into a tighter part of the intensity range.
- **Color Transfer** and **Scalar Opacity** are the two transfer functions as colour ramps. Drag the stops to retune the preset; the opacity ramp carries its value in the alpha channel, which is what the shader reads.
- **Density Scale** is the multiply node that turns opacity into Blender density.

The material also records what it was built from as custom properties (`medblend_preset`, `medblend_preset_window`, and Slicer's `medblend_slicer_ambient`/`_diffuse`/`_specular`/`_specular_power`/`_shade`), visible in `Material Properties > Custom Properties`.

### What is and is not carried over

Colours are converted from Slicer's sRGB display values into Blender's scene-linear colour space, so hues match rather than rendering washed out. Two parts of a Slicer preset have no Blender equivalent and are not applied: the gradient opacity functions, because shader nodes cannot read a volume's gradient magnitude, and the Phong shading parameters, because Blender's volume shader is physically based - those are recorded on the material for reference instead.

The presets are reproduced from Slicer under its BSD-style licence; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). To refresh them from a newer Slicer release, run `python "development scripts/generate_preset_data.py"`.

## Converting CT volumes into a mesh

Rather than viewing the DICOM data as a volume, it is possible to convert the CT data into a mesh. This can be performed by apply the volume to mesh modifier in Blender. 

Start by creating a place-holder object. From the add menu, add a cube into the scene. This cube object will hold the volume to mesh modifier. 

![add_cube](https://github.com/drmichaeldouglass/MedBlend/assets/52724915/9f842bce-1a6a-4c7d-8334-1a4c86373e0c)

With the cube selected, go to the modifier menu, select Add Modifier and add a Volume to Mesh modifier.
![volume_to_mesh](https://github.com/drmichaeldouglass/MedBlend/assets/52724915/7f940498-9199-4bc3-b13e-75f76834846a)

From the object property, select the CT volume, then adjust the threshold to isolate the tissue you want. Because MedBlend normalises image volumes to `0 - 1`, the threshold lives in that range too - around `0.4` is a good starting point for bone in a typical CT, and lower values pick up soft tissue. Use the `medblend_intensity_min`/`medblend_intensity_max` custom properties on the volume if you need to pick a threshold for a specific HU value.

![volume_to_mesh_select_CT](https://github.com/drmichaeldouglass/MedBlend/assets/52724915/decbcaab-e009-4f8a-b5a3-eb1d1cec4795)

This is what the mesh should look like at a threshold that isolates bone. You can apply this modifier from the Volume to Mesh modifier panel to bake the mesh which will allow for manual adjustments.

![CT_Mesh](https://github.com/drmichaeldouglass/MedBlend/assets/52724915/c8b74c1d-baa3-4962-b29e-5eff716fb3f8)

Here are some examples:

A CT scan, structures and dose volumes imported and overlayed. 

![Dose](https://user-images.githubusercontent.com/52724915/220470967-dd2b78f5-c34b-4c70-a5a5-fcea588e37a8.GIF)

DICOM structures for a test prostate radiotherapy plan showing organs at risk such as prostate, urethra, bladder, rectum and the external structure.

![Structure](https://user-images.githubusercontent.com/52724915/220471006-f343c851-915e-4b51-ada2-8164aebb3ae5.GIF)

A test proton therapy plan on a phantom. The CT images, dose distribution and proton spots are shown.

![Proton](https://user-images.githubusercontent.com/52724915/226314672-d9df0645-27b0-4a92-a315-d1a19d69b526.GIF)



## Development

Install the dependencies for the unit tests and run them outside Blender:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```

Validate and build the installable extension with Blender's official commands:

```bash
blender --command extension validate .
blender --command extension build --source-dir . --output-dir dist
blender --command extension validate dist/medblend-2.0.0.zip
```

Upload the archive produced by `extension build` to the Blender Extensions platform. Do not upload the repository or GitHub's generated source archive. GitHub Actions runs the unit tests and builds and validates the extension package for every push and pull request.

## Known Issues
- Not tested on MRI, SPECT, PET or other imaging modalities.
- CT/MR series and RT Dose grids must have uniform slice/plane spacing. MedBlend
  rejects non-uniform or duplicate positions because a single OpenVDB volume
  cannot preserve them without resampling.
- Contours are rasterised using an even-odd point-in-polygon test sampled at voxel centres, so a structure boundary is resolved to the nearest voxel. Small structures relative to the CT voxel size will show that quantisation.
- Imported CT, dose, structure, and proton spot objects are now all placed in the DICOM patient coordinate system (millimetres mapped to metres), so they co-register automatically regardless of import order. Note that the CT volume is therefore no longer centred at the world origin.
- Proton beam orientation (gantry and couch rotation) assumes a head-first supine (HFS) patient; other patient orientations have not been verified and a warning is shown when the plan reports a different patient position.
- If the bundled dependency is missing from the installed package, MedBlend will fail to load. Reinstall using the official extension archive and ensure the `wheels/` directory is included.

Please report bugs through [GitHub Issues](https://github.com/drmichaeldouglass/MedBlend/issues).

## Future Updates

### Import Radiation Therapy Plan Files

Import radiation therapy DICOM plan files to visualise MLC or proton spot positions in the patient CT

### Import Brachytherapy Dwell Points

Visualise brachytherapy dwell point positions and dwell times

### Treatment simulation with Linac model.


## License

MedBlend is released under the [GNU General Public License v3.0 or later](LICENSE). The bundled `pydicom` wheel remains under its upstream licence; see [Third-party notices](THIRD_PARTY_NOTICES.md).

## How to cite

MedBlend: A Medical Visualisation Add-On for Blender, M.Douglass
https://github.com/drmichaeldouglass/MedBlend

DOI: 10.5281/zenodo.10633327

## References
