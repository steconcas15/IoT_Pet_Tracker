# Iot Pet Tracker - Pet Detection Module

A simple and lightweight Python module that detects whether a pet (dog or cat) is present in an image using the YOLO (You Only Look Once) object detection model.

---

## What It Does

* Loads the pre-trained **YOLO11 Large (`yolo11l.pt`)** model.
* Checks images captured by IoT cameras (e.g., ESP32-CAM).
* Filters specifically for pets using COCO dataset classes:
  * **Class 15:** Cat
  * **Class 16:** Dog
* Ignores non-pet objects (humans, furniture, background noise) directly during inference.
* Returns a simple `True` or `False` based on whether a pet was detected.

---

## File Structure

Make sure your weights file is placed inside the `yolov11_model` folder next to the detector script:

```
vision/
├── detector.py             # The PetDetector class module
└── yolov11_model/
    └── yolo11l.pt          # Pre-trained YOLO11 Large weights file
```
