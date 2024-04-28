import sys
import os
import site
import bpy
import importlib


def verify_user_sitepackages(mda_path):
    """
    Checks to see if the user site-packages directory is in the python path
    
    """
    usersitepackagespath = site.getusersitepackages()


    if os.path.exists(usersitepackagespath) and usersitepackagespath not in sys.path:
        sys.path.append(usersitepackagespath)
    if os.path.exists(mda_path) and mda_path not in sys.path:
        sys.path.append(mda_path)




def check_dependencies():
    """
    Checks if the required python modules are installed
    """
    def is_module_installed(module_name):
        try:
            __import__(module_name)
            return True
        except ImportError:
            return False
    current_path = bpy.path.abspath(os.path.dirname(__file__))
    with open(current_path+'/requirements.txt') as f:
        for line in f:
            module_name = line.strip().split('==')[0]  # Remove version if present
            
            # Invalidate the import cache to ensure that the latest version of the module is imported
            importlib.invalidate_caches()  # Invalidate the import cache

            #print('Checking for module:', module_name)
            if not is_module_installed(module_name):
                print(f"Module '{module_name}' is not installed")

                return False  # Return 0 as soon as a missing module is found

    return True  # Return 1 if all modules are installed

#a function to install the required python modules
def install_python_modules():
    """
    Installs the required python modules
    """

    import subprocess
    import platform

    def isWindows():
        return os.name == 'nt'

    def isMacOS():
        return os.name == 'posix' and platform.system() == "Darwin"

    def isLinux():
        return os.name == 'posix' and platform.system() == "Linux"

    def python_exec():
        import sys
        if isWindows():
            return os.path.join(sys.prefix, 'bin', 'python.exe')
        elif isMacOS():
            try:
                # 2.92 and older
                path = bpy.app.binary_path_python
            except AttributeError:
                # 2.93 and later
                import sys
                path = sys.executable
            return os.path.abspath(path)
        elif isLinux():
            return os.path.join(sys.prefix, 'sys.prefix/bin', 'python')
        else:
            print("sorry, still not implemented for ", os.name, " - ", platform.system)

    def installModule(packageName):
        try:
            subprocess.call([python_exe, "import ", packageName])
        except:
            python_exe = python_exec()
           # upgrade pip
            subprocess.call([python_exe, "-m", "ensurepip"])
            subprocess.call([python_exe, "-m", "pip", "install", "--upgrade", "pip"])
           # install required packages
            subprocess.call([python_exe, "-m", "pip", "install", packageName])
    current_path = bpy.path.abspath(os.path.dirname(__file__))
    with open(current_path+'/requirements.txt') as f:
        for line in f:
            # Strip off any whitespace and ignore empty lines
            module = line.strip()
            if module:
                installModule(module)
    
    #credit to luckychris https://github.com/luckychris
    return 1  


