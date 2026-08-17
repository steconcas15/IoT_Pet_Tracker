"""
Telegram Webhook Routing Module
===============================
This module defines the Flask Blueprint responsible for exposing a secure Webhook 
endpoint to the public internet. It intercepts incoming HTTPS POST requests from 
the Telegram API, deserializes the JSON payloads, and safely delegates them to 
the isolated asynchronous event loop managing the Telegram Bot application.
"""

from flask import Blueprint, request
from telegram import Update

# Instantiate the Blueprint for modular integration with the main Flask application
bot_webhook = Blueprint("bot_webhook", __name__)

# ==============================================================================
# GLOBAL STATE CACHE
# ==============================================================================
# Global variables utilized to preserve the in-memory references to the Telegram 
# application and its dedicated asyncio event loop across disparate HTTP requests.
telegram_application = None
telegram_loop = None

def init_telegram_routes(app_instance, loop_instance):
    """
    Caches the asynchronous Telegram application instance and its associated 
    event loop at the module level. This dependency injection allows the synchronous 
    Flask routes to interact with the asynchronous bot framework.
    
    Args:
        app_instance: The fully initialized telegram.ext.Application object.
        loop_instance: The specific asyncio event loop allocated for the bot.
    """
    global telegram_application, telegram_loop
    telegram_application = app_instance
    telegram_loop = loop_instance

@bot_webhook.route("/telegram", methods=["POST"])
def telegram_webhook_handler():
    """
    Primary ingestion endpoint for Telegram Webhook updates.
    Intercepts incoming HTTP POST payloads, reconstructs the object state, 
    and dispatches it to the bot's processing pipeline.
    
    Returns:
        tuple: A standard HTTP 200 OK response to acknowledge receipt to Telegram servers.
    """
    if request.method == "POST":
        # Deserialize the incoming raw JSON payload into a native Telegram Update object
        update = Update.de_json(request.get_json(), telegram_application.bot)
        
        # Bridge the synchronous Flask context to the asynchronous Telegram context 
        # by explicitly executing the update processing within the cached event loop
        telegram_loop.run_until_complete(
            telegram_application.process_update(update)
        )
        
        return "OK", 200