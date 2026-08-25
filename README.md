# Pet Tracker - IoT Digital Twin System

An IoT system based on **Digital Twin (DT)** architecture for the tracking, real-time monitoring, and behavioral training of pets (dogs and cats) in indoor environments.

The system allows you to define allowed or forbidden rooms (*allowed* / *forbidden*), track movements through a two-step verification mechanism (ultrasonic detection + AI visual verification), and promptly deter the pet using a wearable module with an active buzzer in case of restricted room violations.

---

## System Architecture

The overall architecture is divided into **three macro-areas**:

<img width="4216" height="2056" alt="Architettura_overview" src="https://github.com/user-attachments/assets/c17aead6-6dbc-4678-b2ac-4886bc82c7ac" />


---

## Main Components

### 1. On-Field Hardware Nodes
* **Passage Detection Module (ESP8266 + HC-SR04):**
  * Differential algorithm to detect passage and avoid false positives.
  * Sends the trigger event via MQTT to the `home/<door_id>` topic.
* **Visual Acquisition Module (ESP32-CAM OV2640):**
  * Listens on the room's MQTT topics.
  * Upon receiving a trigger event, it captures a frame (using the LED flash if necessary) and sends it to the backend via a JWT-authenticated `HTTP POST multipart/form-data`.
* **Acoustic Deterrence Module (ESP8266 + KY-0012 Active Buzzer):**
  * Battery-powered wearable module (collar/harness).
  * Receives commands on the MQTT topic `home/sound` (`ON`/`OFF`) automatically (in case of a violation) or manually from the administrator.

### 2. Digital Twin & Virtualization Layer (Resource VO Model)
The system models entities as atomic and decoupled resources (*Resource VO*):
* **Door DR:** Monitors the connection status of the ultrasonic sensor and decouples physical passage from visual capture.
* **Room DR:** Camera status, permissions (`allowed`/`forbidden`), occupancy status (`occupied`/`empty`), and daily dwell metrics.
* **Pet DR:** Wearable buzzer status, current room (`current_room`), violation history, and behavioral analytics.
* **User Entity:** Credentials management, roles (*Admin* for `owned_homes`, *Viewer* for `viewable_homes`), and 2FA tokens (OTP).

### 3. Service Layer
* **Database Service:** Management of MongoDB collections (`digital_twins`, `digital_replicas`, `users`).
* **MQTT Status Service:** Real-time monitoring via *Last Will and Testament* (LWT) on `home/+/state` with anti-flickering timers (30s disconnection alert, 10s recovery notification).
* **Pet Detection Service:** AI inference via the **YOLO11** model to distinguish the pet from people or robot vacuums and execute the room transition.
* **Room & Pet Statistics Services:** Aggregation of room dwell times and calculation of the pet's learning/obedience trends (*Learning*, *Trained*, *Regressing*, *Stationary*).

### 4. Client Interfaces
* **Web Application:** Management dashboard protected by JWT/2FA for layout configuration (rooms, doors), permissions, statistical charts, and role management (*Admin* / *Viewer*).
* **Telegram BOT:** Immediate push notifications for intrusions and disconnections, OTP code reception, location queries (`/locate`), and manual buzzer activation (`/buzzer`).

---

## Getting Started

### Prerequisites
* **Python 3.8+**
* **MongoDB Community / Atlas**
* **HiveMQ Cloud Account** (or any MQTT broker with TLS support on port 8883)
* **Ngrok** (to expose the Telegram Bot webhook)
* **Arduino IDE / ESP-IDF** (for flashing the NodeMCU and ESP32-CAM nodes)

### Environment Setup

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/IoT_Pet_Tracker.git
cd IoT_Pet_Tracker

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

## Telegram BOT Commands

* `/start` - Start the bot and display the onboarding menu.
* `/login <username> <password>` - Link your account and select the environment to manage (the password is automatically deleted from the chat).
* `/locate` - Real-time query of the room where the pet is currently located.
* `/buzzer` - Manually activate/deactivate the acoustic signal on the collar (function reserved for the Admin; disabled if the pet is already in a forbidden room).
* `/logout` - Terminate the active session.
* `/help` - Command guide.

---

## Authors & Credits
Project for the **Internet of Things (IoT)** class - Academic Year 2025/2026  
*MSc Electronic Engineering - University of Cagliari (Università degli Studi di Cagliari)*  

* **Marco Fois**
* **Stefano Concas**
