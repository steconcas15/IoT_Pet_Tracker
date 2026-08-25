# IoT Pet Tracker — Firmware Suite

This repository contains the firmware suite for the Object operating in the **Home environment**, designed for presence monitoring, indoor pet tracking, event-triggered image acquisition, and acoustic alarms for restricted room access.

---

## Repository Structure

```
.
├── ESP-32S_Camera/
│   ├── ESP-32S_Camera.ino      # Main camera firmware: JWT Auth, MQTT trigger, image capture & multipart upload
│   ├── board_config.h          # Hardware camera model selector (AI Thinker default)
│   └── camera_pins.h           # GPIO pin mappings for supported camera modules
├── NodeMCU_Ultrasonic/
│   └── NodeMCU_Ultrasonic.ino  # Adaptive threshold presence detection & MQTT trigger publisher
└── NodeMCU_Buzzer/
    └── NodeMCU_Buzzer.ino      # Alarm receiver from backend for buzzer activation/deactivation
```

---

## Hardware & Pinout Specifications

### 1. ESP32-CAM (AI Thinker ESP32-CAM)
* **Function:** Captures images when triggered by pet movement and performs an HTTP multipart upload to the Flask server after acquiring a JWT authentication token.
* **Hardware:** ESP32-CAM module with onboard OV2640 camera sensor and high-power flash LED (GPIO 4).

### 2. NodeMCU Ultrasonic Sensor (HC-SR04)
* **Function:** Samples distance at a 2 Hz frequency (every 500 ms) to detect entry and exit events across door thresholds using a delta-variation algorithm.
* **Pin Connections:**
  | HC-SR04 Sensor | NodeMCU (ESP-12E Module) Pin |
  |:---------------|:-----------------------------|
  | **VCC**        | `VU` / `5V`                  |
  | **GND**        | `GND`                        |
  | **TRIG**       | `D5` (GPIO 14)               |
  | **ECHO**       | `D6` (GPIO 12)               |

### 3. NodeMCU Buzzer
* **Function:** Continuous acoustic buzzer controlled via MQTT (`home/sound`), activated when an unauthorized pet enters a restricted room.
* **Pin Connections:**
  | Buzzer Module  | NodeMCU (ESP-12E Module) Pin |
  |:---------------|:-----------------------------|
  | **VCC / +**    | `3V3` or `VIN`               |
  | **GND / -**    | `GND`                        |
  | **I/O (Data)** | `D0` (GPIO 16)               |

---

## Parameter Setup

Before flashing the microcontrollers, update the following placeholders in each `.ino` source file:

```cpp
// 1. Wi-Fi Configuration
const char *ssid = "YOUR_WIFI_SSID";
const char *password = "YOUR_WIFI_PASSWORD";

// 2. MQTT Broker (HiveMQ Cloud - TLS 8883)
const char* mqtt_server = "xxxxxxxxxxxx.s1.eu.hivemq.cloud"; 
const int   mqtt_port = 8883; 
const char* mqtt_user = "YOUR_MQTT_USERNAME";
const char* mqtt_password = "YOUR_MQTT_PASSWORD";

// 3. Digital Twin Identifiers (obtained from the Web Application)
const char* home_id = "YOUR_HOME_ID";
const char* room_id = "YOUR_ROOM_ID";
const char* door_id = "YOUR_DOOR_ID";
const char* pet_id  = "YOUR_PET_ID";

// 4. Flask Server Endpoint (ESP-32S_Camera only)
const char* server_ip = "192.168.1.xxx"; // Local or remote backend IP
const int   server_port = 5000;
```
