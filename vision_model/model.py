import os
import cv2
from ultralytics import YOLO

class PetDetector:

    def __init__(self):
        """Initializes the detector with the Large model.

        Using the YOLO11l model for a great balance between 
        high precision and manageable file size.
        """
        # 1. Trova il percorso assoluto della cartella in cui si trova QUESTO file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 2. Unisci il percorso della cartella al nome del file del modello
        model_path = os.path.join(current_dir, "yolov11_model", "yolo11l.pt")

        # 3. Passa il percorso assoluto a YOLO[cite: 2]
        print(f"[YOLO] Caricamento modello da: {model_path}")
        self.model = YOLO(model_path)

        # Definiamo una lista di ID corrispondenti ai pet accettati.
        # 15 = cat, 16 = dog (dataset COCO standard).
        # Aggiungi qui l'ID del coniglio se usi un modello custom.
        self.pet_classes = [15, 16]

    def detect_any_pet(self, image_path: str) -> bool:
        """Checks if ANY target animal is present in the image.

        Arguments:
            image_path: path to the image file

        Returns:
            bool: True if found with conf >= 0.25, False otherwise.
        """
        # Filtriamo direttamente a livello YOLO passando l'intera lista di ID pet.
        # Questo ignora tutti gli altri oggetti (sedie, libri, ecc.)[cite: 2].
        results = self.model(
            image_path, conf=0.25, classes=self.pet_classes, verbose=False
        )
        result = results[0]

        # Returns True if ANY pet is found, False otherwise[cite: 2]
        return len(result.boxes) > 0