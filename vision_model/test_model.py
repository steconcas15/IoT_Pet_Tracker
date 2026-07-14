from model import PetDetector

# 1. Initialize the detector (it loads the weights automatically from 'weights/yolov8n.pt')
detector = PetDetector()


# 2. Wrapper function called by your application logic
def check_animal_presence(image_path: str, animal_to_find: str) -> bool:
    """Wrapper function that ONLY requires the image path and the target animal ('dog' or 'cat')."""
    found = detector.detect_target(image_path, target=animal_to_find)

    if found:
        print(f"✅ Detected {animal_to_find} in {image_path}!")
    else:
        print(f"❌ No {animal_to_find} detected in {image_path}.")

    return found


# =====================================================================
# CLEAN TEST EXECUTION
# =====================================================================
if __name__ == "__main__":
    # Test case 1: Check for a dog
    is_dog_here = check_animal_presence("cane.png", "dog")

    # Test case 2: Check for a cat
    is_cat_here = check_animal_presence("cane.png", "cat")