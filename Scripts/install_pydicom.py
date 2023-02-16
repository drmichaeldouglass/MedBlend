import subprocess
import sys
import os
import site

def verify_user_sitepackages(mda_path):
    usersitepackagespath = site.getusersitepackages()

    if os.path.exists(usersitepackagespath) and usersitepackagespath not in sys.path:
        sys.path.append(usersitepackagespath)
    if os.path.exists(mda_path) and mda_path not in sys.path:
        sys.path.append(mda_path)

# path to python.exe
python_exe = os.path.realpath(sys.executable)

# upgrade pip
subprocess.call([python_exe, "-m", "ensurepip"])
subprocess.call([python_exe, "-m", "pip", "install",
                "--upgrade", "pip"], timeout=600)

# install required packages
subprocess.call([python_exe, "-m", "pip", "install", "pydicom"], timeout=600)


def verify_user_sitepackages(package_location):
    if os.path.exists(package_location) and package_location not in sys.path:
        sys.path.append(package_location)


verify_user_sitepackages(site.getusersitepackages())

try:
    import pydicom
    pydicom_install_successful = True
except:
    pydicom_install_successful = False
