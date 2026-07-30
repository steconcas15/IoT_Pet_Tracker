import cv2
from ultralytics import YOLO


class PetDetector:

    def __init__(self):
        """Initializes the detector with the Large model.

        Using the YOLO11l model for a great balance between 
        high precision and manageable file size.
        """
        # Passiamo al modello Large. 
        # Ultralytics lo scaricherà in automatico se non lo trova.
        self.model_name = "yolo11l.pt"

        print(f"[YOLO] Loading Large model: {self.model_name}...")
        self.model = YOLO(self.model_name)

        # Text mapping for standard COCO dataset classes (English only)
        self.class_mapping = {
            "cat": 15,
            "dog": 16,
        }

    def detect_target(self, image_path: str, target: str) -> bool:
        """Checks if the target animal is present in the image.

        Arguments:
            image_path: path to the image file
            target: 'dog' or 'cat'

        Returns:
            bool: True if found with conf >= 0.25, False otherwise.
        """
        target_clean = target.lower().strip()

        if target_clean not in self.class_mapping:
            raise ValueError(
                f"Target '{target}' is invalid. Choose between: 'dog' or 'cat'."
            )

        target_class_id = self.class_mapping[target_clean]

        # Filter directly at the YOLO level: only target class with conf >= 0.25.
        # This completely ignores other objects (chairs, books, etc.) at the source.
        results = self.model(
            image_path, conf=0.25, classes=[target_class_id], verbose=False
        )
        result = results[0]

        # Returns True if the target is found, False otherwise
        return len(result.boxes) > 0