from vision_model.model import PetDetector 

class PetDetectionService:
    def __init__(self):
        self.name = "PetDetectionService"
        self.config = {}
        # Inizializziamo il modello YOLO una sola volta all'avvio del servizio
        self.detector = PetDetector()

    def configure(self, config: dict):
        """Configura il servizio con eventuali parametri opzionali dal DB"""
        self.config = config

    def process_image(self, image_path: str, target: str) -> bool:
        """Esegue l'inferenza tramite il detector YOLO"""
        return self.detector.detect_target(image_path, target)