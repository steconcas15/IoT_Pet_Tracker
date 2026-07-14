import cv2
from ultralytics import YOLO


def classifica_pet(model_path: str, image_path: str) -> str:
    """Carica il modello YOLO specificato, analizza l'immagine e restituisce

    una stringa che descrive se ha trovato un cane, un gatto, entrambi o nulla.
    """
    # 1. Carica il modello dal path fornito
    model = YOLO(model_path)

    # ID delle classi nel dataset COCO: 15 = gatto, 16 = cane
    pet_classes = [15, 16]

    # 2. Esegue l'inferenza filtrando solo per cani e gatti
    results = model(image_path, conf=0.4, classes=pet_classes, verbose=False)
    result = results[0]

    # 3. Analizza i box trovati per decidere la label di ritorno
    trovato_gatto = False
    trovato_cane = False

    for box in result.boxes:
        class_id = int(box.cls[0])
        if class_id == 15:
            trovato_gatto = True
        elif class_id == 16:
            trovato_cane = True

    # 4. Ritorna la label testuale basata sui rilevamenti
    if trovato_cane and trovato_gatto:
        return "both"
    elif trovato_cane:
        return "dog"
    elif trovato_gatto:
        return "cat"
    else:
        return "nothing"


# =====================================================================
# ESEMPIO DI UTILIZZO (Modifica i path con i tuoi file reali):
# =====================================================================
if __name__ == "__main__":
    PATH_MODELLO = "weights/yolov8n.pt"
    PATH_IMMAGINE = "cane.png"

    label_risultato = classifica_pet(PATH_MODELLO, PATH_IMMAGINE)
    print(f"Risultato classificazione: {label_risultato}")