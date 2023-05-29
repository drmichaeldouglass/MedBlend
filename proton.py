def is_proton_plan(ds):
    """
    Checks if the DICOM file at the given path is of type dose.
    Returns True if it is, False otherwise.
    """
    try:
        if ds.Modality == 'RTIon':
            return True
        else:
            return False
    except:
        return False