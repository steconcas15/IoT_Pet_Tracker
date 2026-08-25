"""
Telegram HTTP Notification Dispatcher
=====================================
This module handles direct outbound communication to the Telegram API via synchronous 
HTTP POST requests. It decouples critical alerts (intrusions, OTPs, offline hardware) 
from the asynchronous `python-telegram-bot` event loop, ensuring immediate delivery 
even when triggered by background threads or external MQTT callbacks.
"""

import requests
from flask import current_app
from src.application.bot.handlers.login_handlers import LOGGED_USERS
from src.application.bot.config.settings import TELEGRAM_TOKEN

# State dictionary to track dispatched offline alerts for future cleanup.
# Format: home_id -> [(chat_id, message_id), ...]
ACTIVE_OFFLINE_ALERTS = {}

def send_unauthorized_room_alert(room_name):
    """
    Dispatches an immediate intrusion alert via a direct HTTP POST request 
    to the Telegram API, circumventing asynchronous loop constraints.
    
    Args:
        room_name (str): The name of the unauthorized zone where the pet was detected.
    """
    if not TELEGRAM_TOKEN:
        print("[TELEGRAM] Token not configured for direct dispatch.")
        return

    alert_text = (
        f"🚨 **INTRUSION ALARM!** 🚨\n\n"
        f"Your pet has just been detected in **{room_name}**, "
        f"a zone where entry is strictly unauthorized!"
    )
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    # Broadcast the alert to all authenticated users utilizing standard HTTP requests
    for chat_id in LOGGED_USERS.keys():
        payload = {
            "chat_id": chat_id,
            "text": alert_text,
            "parse_mode": "Markdown"
        }
        try:
            response = requests.post(url, json=payload, timeout=3)
            if response.status_code == 200:
                print(f"[TELEGRAM] HTTP Alert successfully dispatched to user {chat_id}")
            else:
                print(f"[TELEGRAM] Telegram API Error ({response.status_code}): {response.text}")
        except Exception as e:
            print(f"[TELEGRAM] Network error during alert dispatch: {e}")


def send_otp_to_telegram(user_id, otp_code):
    """
    Transmits a One-Time Password (OTP) directly to the user's Telegram chat 
    via HTTP POST, independent of incoming command polling.
    
    Args:
        user_id (str): The database identifier of the target user.
        otp_code (str): The securely generated 6-digit challenge.
        
    Returns:
        bool: True if the dispatch succeeded, False otherwise.
    """
    if not TELEGRAM_TOKEN:
        print("[TELEGRAM] Token not configured for direct dispatch.")
        return False

    # Resolve the Telegram chat ID mapped to the database user ID
    target_chat_id = None
    for t_id, user_data in LOGGED_USERS.items():
        if str(user_data["user_id"]) == str(user_id):
            target_chat_id = t_id
            break

    if not target_chat_id:
        print(f"[TELEGRAM] No active Telegram session found for user {user_id}. Execute /login first.")
        return False

    message_text = (
        f"🔐 **OTP Verification Code** 🔐\n\n"
        f"Your temporary access code is: `{otp_code}`\n"
        f"This code will expire in 5 minutes. Enter it in the web interface to confirm the operation."
    )
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": target_chat_id,
        "text": message_text,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=3)
        if response.status_code == 200:
            print(f"[TELEGRAM] OTP successfully dispatched to user {target_chat_id}")
            return True
        else:
            print(f"[TELEGRAM] Telegram API Error ({response.status_code}): {response.text}")
            return False
    except Exception as e:
        print(f"[TELEGRAM] Network error during OTP dispatch: {e}")
        return False


def send_offline_alert(home_id, offline_devices, all_offline):
    """
    Dispatches a direct HTTP alert to active session users when the MQTT watchdog 
    detects hardware disconnection. Caches message IDs to allow for future UI cleanup.
    
    Args:
        home_id (str): The environment identifier experiencing the outage.
        offline_devices (list): Array of device names currently unreachable.
        all_offline (bool): Flag indicating a total environment blackout.
    """
    # Local imports utilized to prevent circular dependency resolution issues
    from bot.handlers.login_handlers import LOGGED_USERS
    from bot.config.settings import TELEGRAM_TOKEN
    import requests

    if not TELEGRAM_TOKEN:
        return

    # Initialize the tracking array for this specific home if it does not exist
    if home_id not in ACTIVE_OFFLINE_ALERTS:
        ACTIVE_OFFLINE_ALERTS[home_id] = []

    if all_offline:
        alert_text = (
            "🔌 **CONNECTION ALARM** 🔌\n\n"
            "All devices in the home are currently **OFFLINE**.\n"
            "This indicates a potential router/Wi-Fi failure or a power outage!"
        )
    else:
        # Sanitize device names for Markdown compatibility
        safe_devices = [str(d).replace("_", "\\_").replace("*", "") for d in offline_devices]
        devices_list = "\n".join([f"• {d}" for d in safe_devices])
        alert_text = (
            "⚠️ **WARNING: Offline Devices** ⚠️\n\n"
            "The following devices have lost connectivity:\n"
            f"{devices_list}"
        )

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    # Filter logged users to only alert those associated with the affected environment
    for chat_id, user_data in LOGGED_USERS.items():
        if str(user_data.get("home_id")) == str(home_id):
            payload = {
                "chat_id": chat_id,
                "text": alert_text,
                "parse_mode": "Markdown"
            }
            try:
                response = requests.post(url, json=payload, timeout=3)
                if response.status_code == 200:
                    print(f"[TELEGRAM] Offline Alert dispatched to user {chat_id}")
                    
                    # CAPTURE MESSAGE ID FOR SUBSEQUENT DELETION UPON RECOVERY
                    data = response.json()
                    msg_id = data.get("result", {}).get("message_id")
                    if msg_id:
                        ACTIVE_OFFLINE_ALERTS[home_id].append((chat_id, msg_id))
                else:
                    print(f"[TELEGRAM ERROR] Unable to dispatch alert. Code {response.status_code}: {response.text}")
            except Exception as e:
                print(f"[TELEGRAM] Network error during offline alert dispatch: {e}")


def send_online_recovery(home_id):
    """
    Purges previous offline error messages from the chat UI and broadcasts 
    a system recovery notification once all devices return online.
    
    Args:
        home_id (str): The environment identifier that has recovered.
    """
    from bot.handlers.login_handlers import LOGGED_USERS
    from bot.config.settings import TELEGRAM_TOKEN
    import requests

    if not TELEGRAM_TOKEN:
        return

    # Verify if active alarms exist in the cache for this environment
    alerts = ACTIVE_OFFLINE_ALERTS.get(home_id, [])
    if not alerts:
        return  # No active alarms to clear; exit silently

    # 1. PURGE PREVIOUS ERROR MESSAGES FROM TELEGRAM UI
    delete_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteMessage"
    for chat_id, msg_id in alerts:
        try:
            requests.post(delete_url, json={"chat_id": chat_id, "message_id": msg_id}, timeout=3)
        except Exception as e:
            print(f"[TELEGRAM] Error deleting legacy alert: {e}")

    # 2. DISPATCH THE "SYSTEM RECOVERED" CONFIRMATION
    alert_text = (
        "✅ **SYSTEM RECOVERED** ✅\n\n"
        "All devices in the home environment are operating normally and are **ONLINE**."
    )
    send_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    for chat_id, user_data in LOGGED_USERS.items():
        if str(user_data.get("home_id")) == str(home_id):
            payload = {
                "chat_id": chat_id,
                "text": alert_text,
                "parse_mode": "Markdown"
            }
            try:
                requests.post(send_url, json=payload, timeout=3)
            except Exception as e:
                pass  # Fail silently for recovery messages to prevent log bloat

    # Reset the alarm tracking array for this environment
    ACTIVE_OFFLINE_ALERTS[home_id] = []