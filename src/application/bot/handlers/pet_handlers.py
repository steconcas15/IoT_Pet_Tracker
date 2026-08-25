"""
Telegram Bot Handlers Module: Pet Localization & Buzzer Control
===============================================================
This module defines asynchronous event handlers for the Telegram bot interface. 
It enables authenticated users to interact with their Digital Twin environments, 
specifically providing spatial tracking (localization) and manual hardware 
actuation (buzzer control) while enforcing strict security and authorization policies.
"""

from telegram import Update
from telegram.ext import ContextTypes
from datetime import datetime, timezone
from src.application.bot.handlers.login_handlers import LOGGED_USERS

async def locate_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the /locate command to fetch and report the pet's current spatial context.
    
    Validates user session, extracts the active Digital Twin, and traverses its 
    replicas to determine the room currently occupied by the pet.
    """
    telegram_id = update.effective_user.id
    if telegram_id not in LOGGED_USERS:
        await update.message.reply_text("⚠️ You must /login first.")
        return

    # Extract user identification and the active home context from the session state
    user_data = LOGGED_USERS[telegram_id]
    user_id = user_data["user_id"]
    home_id = user_data["home_id"]

    if not home_id:
        await update.message.reply_text("No home environment selected. Please /login again to choose one.")
        return

    db_service = context.bot_data["db_service"]
    dt_factory = context.bot_data["dt_factory"]

    try:
        # Access the Digital Twin instance selected during the login phase
        dt_data = dt_factory.get_dt(home_id)
        
        if not dt_data:
            await update.message.reply_text("Error: Unable to locate the selected home environment.")
            return
            
        # Traverse the digital replicas to locate the pet entity
        pet_dr = None
        for replica in dt_data.get("digital_replicas", []):
            if replica.get("type") == "pet":
                pet_dr = db_service.get_dr("pet", replica.get("id"))
                break
        
        if not pet_dr:
            await update.message.reply_text("No pet found associated with your environment.")
            return

        pet_name = pet_dr.get("profile", {}).get("name", "Your pet")
        current_room = pet_dr.get("data", {}).get("current_room", "unknown")
        
        await update.message.reply_text(f"📍 **{pet_name}** is currently located in: **{current_room}**", parse_mode='Markdown')

    except Exception as e:
        await update.message.reply_text(f"Error during localization: {str(e)}")


async def buzzer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the /buzzer command, granting manual control over the deterrent hardware.
    
    Security Policies Enforced:
    1. Role-Based Access: Only the administrator (owner) of the home can execute this command.
    2. Spatial Constraints: Manual activation is strictly prohibited if the pet is located 
       in a 'forbidden' zone, as the security subsystem autonomously manages the buzzer in these areas.
    """
    telegram_id = update.effective_user.id
    if telegram_id not in LOGGED_USERS:
        await update.message.reply_text("⚠️ You must /login first.")
        return

    # Extract user identification and the active home context from the session state
    user_data = LOGGED_USERS[telegram_id]
    user_id = user_data["user_id"]
    home_id = user_data["home_id"]

    if not home_id:
        await update.message.reply_text("No home environment selected. Please /login again to choose one.")
        return

    db_service = context.bot_data["db_service"]
    dt_factory = context.bot_data["dt_factory"]
    mqtt_manager = context.bot_data["mqtt_manager"]

    try:
        # SECURITY GATE: Verify that the requesting user holds administrative rights for the selected home
        user = db_service.get_user_by_id(user_id)
        if not user:
            await update.message.reply_text("Error: User not found in the database.")
            return
            
        owned_homes = user.get("data", {}).get("owned_homes", [])
        if home_id not in owned_homes:
            await update.message.reply_text("⛔ Access Denied: Only the home administrator can use the /buzzer command.")
            return

        # Directly utilize the session's home ID
        dt_data = dt_factory.get_dt(home_id)
        
        if not dt_data:
            await update.message.reply_text("Error: Unable to locate the selected home environment.")
            return

        pet_id = None
        pet_name = "Your pet"
        pet_dr = None
        
        # Retrieve the persistent Digital Replica of the pet
        for replica in dt_data.get("digital_replicas", []):
            if replica.get("type") == "pet":
                pet_id = replica.get("id")
                pet_dr = db_service.get_dr("pet", pet_id)
                if pet_dr:
                    pet_name = pet_dr.get("profile", {}).get("name", pet_name)
                break
        
        if not pet_dr or not pet_id:
            await update.message.reply_text("No pet found in the current home.")
            return

        # 1. Identify the pet's current location and evaluate the room's permission policies
        current_room_name = pet_dr.get("data", {}).get("current_room")
        
        if not current_room_name:
            await update.message.reply_text("⚠️ Unable to determine the pet's current room.")
            return

        rooms = db_service.query_drs("room", {"profile.name": current_room_name})
        if rooms:
            permission_level = rooms[0].get("profile", {}).get("permission_level", "allowed")
            
            # SECURITY GATE: Prevent manual interference if the pet is in a forbidden zone (system-managed)
            if permission_level == "forbidden":
                await update.message.reply_text(
                    f"⛔ Command restricted! {pet_name} is in **{current_room_name}** "
                    f"(a forbidden zone). The buzzer is currently managed automatically by the security system.",
                    parse_mode='Markdown'
                )
                return

        # 2. Evaluate current hardware state to implement a toggle logic
        current_status = pet_dr.get("data", {}).get("buzzer_state", "OFF")

        if current_status == "ON":
            # Manual deactivation by the user (Updated topic and QoS)
            mqtt_manager.client.publish("home/sound", "OFF", qos=1)
            
            db_service.update_dr(dr_type="pet", dr_id=pet_id, update_data={
                "data.buzzer_state": "OFF"
            })
            
            await update.message.reply_text(f"🔇 **Buzzer deactivated** manually for {pet_name}.", parse_mode='Markdown')
            
        else:
            # Authorized manual activation (Updated topic and QoS)
            mqtt_manager.client.publish("home/sound", "ON", qos=1)
            
            db_service.update_dr(dr_type="pet", dr_id=pet_id, update_data={
                "data.buzzer_state": "ON",
                "data.last_buzzer_start_time": datetime.now(timezone.utc).isoformat()
            })

            # Dispatch contextual feedback with deactivation instructions
            await update.message.reply_text(
                f"🔊 **Buzzer activated** manually for {pet_name} in a safe zone!\n"
                f"Execute the /buzzer command again to deactivate it.", 
                parse_mode='Markdown'
            )

    except Exception as e:
        await update.message.reply_text(f"Error during buzzer interaction: {str(e)}")