import os

wheels_dir = r"/MedBlend/wheels/"
wheel_files = os.listdir(wheels_dir)

wheels = [os.path.join(wheels_dir, wheel_file) for wheel_file in wheel_files if wheel_file.endswith('.whl')]

for wheel in wheels:
    print(f'"{wheel}",')