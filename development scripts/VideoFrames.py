import numpy as np
from PIL import Image
#from moviepy.editor import ImageSequenceClip
import tkinter as tk
from tkinter import filedialog
import os

# Function to normalize images
def normalize_images(images, max_intensity):
    normalized_images = []
    for image in images:
        normalized = (image / max_intensity) * 255.0
        normalized_images.append(normalized)
    return normalized_images

# Create a GUI for directory selection
root = tk.Tk()
root.withdraw()  # Hide the main window
directory = filedialog.askdirectory(title='Select Image Directory')
root.destroy()

# Load images from the selected directory
image_files = sorted([os.path.join(directory, file) for file in os.listdir(directory) if file.endswith('.png')])
images = [Image.open(image) for image in image_files]

# Convert images to numpy arrays for cumulative sum
arrays = [np.array(image) for image in images]

# Perform cumulative sum
cumulative_frames = np.cumsum(arrays, axis=0)

# Normalize images to the maximum pixel intensity of the last cumulative image
max_intensity = np.max(cumulative_frames[-1])
normalized_cumulative_frames = normalize_images(cumulative_frames, max_intensity)

# Convert arrays back to images
cumulative_images = [Image.fromarray(frame.astype(np.uint8)) for frame in normalized_cumulative_frames]

# Save normalized cumulative images if needed
for i, image in enumerate(cumulative_images):
    image.save(f'{directory}/normalized_cumulative_frame{i}.png')

# Create a video clip from the normalized cumulative images
#clip = ImageSequenceClip([image for image in cumulative_images], fps=24)  # Set your fps (frames per second)

# Write the video to a file
#clip.write_videofile('your_video.mp4', codec='libx264')
