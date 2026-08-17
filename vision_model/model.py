"""
Computer Vision Inference Module
================================
This module encapsulates the object detection logic using the YOLO (You Only Look Once) 
architecture. It is specifically configured to identify target animals (pets) within 
images submitted via IoT telemetry, leveraging a pre-trained model on the COCO dataset.
"""

import os
import cv2
from ultralytics import YOLO

class PetDetector:
    """
    A dedicated detector class that wraps the Ultralytics YOLO inference engine.
    It isolates the computer vision logic from the main application routing and services.
    """

    def __init__(self):
        """
        Initializes the detector with the Large YOLO model.

        Using the YOLO11l model provides an optimal balance between 
        high detection precision and manageable computational requirements.
        """
        # 1. Locate the absolute path of the directory containing THIS specific file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 2. Construct the complete file path to the pre-trained model weights
        model_path = os.path.join(current_dir, "yolov11_model", "yolo11l.pt")

        # 3. Instantiate the YOLO model using the resolved absolute path
        print(f"[YOLO] Loading model from: {model_path}")
        self.model = YOLO(model_path)

        # Define a target list of class IDs corresponding to accepted pets.
        # Based on the standard COCO dataset mappings: 15 = cat, 16 = dog.
        # Note: Additional class IDs (e.g., for a rabbit) can be appended here 
        # if migrating to a custom-trained model in the future.
        self.pet_classes = [15, 16]

    def detect_any_pet(self, image_path: str) -> bool:
        """
        Evaluates whether ANY targeted animal is present within the provided image.

        Arguments:
            image_path (str): The absolute or relative path to the telemetry image file.

        Returns:
            bool: True if at least one target pet is found with a confidence threshold >= 0.25, False otherwise.
        """
        # Filter detections directly at the YOLO engine level by supplying the list of target pet IDs.
        # This optimization ensures all non-target objects (e.g., chairs, books, people) are instantly ignored.
        results = self.model(
            image_path, conf=0.25, classes=self.pet_classes, verbose=False
        )
        
        # Extract the first result object (since we are only processing a single image)
        result = results[0]

        # Return True if the bounding box array contains at least one valid detection
        return len(result.boxes) > 0