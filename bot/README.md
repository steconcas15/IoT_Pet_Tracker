# IoT Pet Tracker - Telegram Bot

This module manages the Telegram Bot interface and alerting subsystem for the IoT platform. It connects the asynchronous python-telegram-bot framework with synchronous Flask backend routes, background workers, and MQTT alert events.

---
## Repository Structure

```
bot/
├── config/
│   └── settings.py          # Environment variables and configuration loader
├── handlers/
│   ├── base_handlers.py     # Main handler registry, onboarding (/start, /help) and fallback
│   ├── login_handlers.py    # Authentication, session cache (LOGGED_USERS), home picker
│   └── pet_handlers.py      # Pet location lookup (/locate) and buzzer actuator (/buzzer)
├── routes/
│   └── webhook_routes.py    # Flask Blueprint exposing the /telegram webhook endpoint
└── notifier.py          # Direct HTTP alert dispatcher (intrusions, OTPs, offline watchdog)

```
---

## Handler Overview

### 1. Base Handlers (`base_handlers.py`)
* **`/start` Handler:** Greets new users and tells them how to link their account using `/login`.
* **`/help` Handler:** Shows a list of all available commands and how to use them.
* **Fallback / Echo Handler:** Catches unrecognized text or invalid inputs and suggests typing `/help`.
* **Handler Registry (`setup_bot_handlers`):** The master setup function that connects all commands and inline buttons to the bot in the correct priority order.

### 2. Login Handlers (`login_handlers.py`)
* **`/login <username> <password>` Handler:**
  * Checks your credentials against the MongoDB database.
  * **Automatic Message Deletion:** Instantly deletes your login message from the chat so your password is not left visible.
  * **Home Picker:** If your account has access to multiple homes, it creates clickable inline buttons so you can choose which home to control.
* **Home Selection Callback:** Saves your home selection when you click one of the inline buttons.
* **`/logout` Handler:** Clears your active login session from memory.

### 3. Pet Handlers (`pet_handlers.py`)
* **`/locate` Handler:** Looks up your home's Digital Twin and tells you in which room your pet is currently located.
* **`/buzzer` Handler:**
  * Allows you to turn the deterrent buzzer on or off by sending an MQTT message (`home/sound`).
  * **Owner Check:** Only the owner of the house can use this command.
  * **Forbidden Room Lock:** If your pet is in a forbidden room, you cannot manually toggle the buzzer because the security system is already controlling it automatically.

---

## Command Reference

| Command | Arguments | Required Permission | Description |
|:---|:---|:---|:---|
| `/start` | None | Public | Displays welcome message and getting-started guide. |
| `/help` | None | Public | Lists all commands and syntax. |
| `/login` | `<user> <pass>` | Public | Logs into the system, deletes password message, and selects active home. |
| `/logout` | None | Logged In | Logs out and clears user session. |
| `/locate` | None | Logged In | Queries the Digital Twin to get the pet's current room. |
| `/buzzer` | None | Admin (Owner) | Manually activate/deactivate the deterrent buzzer (locked in forbidden zones). |

---

## Alert Notifications (`notifier.py`)

The notifier sends direct HTTP POST requests to the Telegram API so background tasks and MQTT events can send instant alerts without getting blocked:

* **Intrusion Alerts (`send_unauthorized_room_alert`):** Broadcasts an alarm message when a pet enters an unauthorized room.
* **OTP Dispatch (`send_otp_to_telegram`):** Sends 6-digit authentication codes directly to the user chat.
* **Hardware Offline Watchdog (`send_offline_alert`):** Warns users when one or all IoT devices in a home disconnect. It tracks message IDs so it can clean them up later.
* **Auto Recovery Cleanup (`send_online_recovery`):** Deletes previous offline error messages from the chat once all devices come back online, then posts a recovery confirmation.

---

## Environment Variables Configuration

Create a `.env` file in the root directory:

```env
# Telegram Bot Configuration
TELEGRAM_TOKEN=your_telegram_bot_token

# Ngrok Configuration (for local webhook development)
NGROK_TOKEN=your_ngrok_auth_token

# Server Configuration
PORT=5000
JWT_SECRET_KEY=your_secret_key
```
