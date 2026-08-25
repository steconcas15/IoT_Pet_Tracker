"""
Telegram Bot Handler Registry Module
====================================
This module aggregates and registers all asynchronous event handlers for the 
Telegram bot interface. It provides foundational commands for user onboarding 
(/start, /help) and routes authenticated operations to their respective sub-modules.
"""

from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes, CommandHandler, MessageHandler, filters
from src.application.bot.handlers.login_handlers import login_handler, logout_handler
from src.application.bot.handlers.pet_handlers import locate_handler, buzzer_handler
from src.application.bot.handlers.login_handlers import home_selection_callback

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the /start command, providing initial onboarding instructions 
    and prompting the user to authenticate against the core system.
    """
    welcome_message = (
        "🐾 Welcome to the IoT Pet Tracker Bot!\n\n"
        "To get started, you must link your account.\n"
        "Please authenticate using the command: /login <username> <password>"
    )
    await update.message.reply_text(welcome_message)

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the /help command, displaying a comprehensive catalog of 
    available system operations and their syntax.
    """
    help_text = (
        "🤖 Command Guide:\n"
        "/start - Initialize the bot and display onboarding\n"
        "/login <user> <pass> - Authenticate into the system\n"
        "/logout - Terminate your active session\n"
        "/locate - Locate your pet's current room\n"
        "/buzzer - Manually toggle the deterrent hardware\n"
    )
    await update.message.reply_text(help_text)

async def echo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Fallback handler for unrecognized or malformed text inputs.
    Redirects the user to the help directory to ensure smooth UX.
    """
    await update.message.reply_text("Unrecognized command. Please type /help for a list of available operations.")

def setup_bot_handlers(application):
    """
    Registers and binds all event handlers to the core Telegram application lifecycle.
    Implements a strict priority-based routing chain.
    
    Args:
        application: The instantiated telegram.ext.Application object.
    """
    
    # Core system commands
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("help", help_handler))
    
    # Authentication & Session Management
    application.add_handler(CommandHandler("login", login_handler))
    application.add_handler(CommandHandler("logout", logout_handler))
    
    # IoT Digital Twin Operations
    application.add_handler(CommandHandler("locate", locate_handler))
    application.add_handler(CommandHandler("buzzer", buzzer_handler))
    
    # Fallback filter (must remain at the end of the registry chain to catch unhandled inputs)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo_handler))
    
    # Callback query routing for inline keyboard interactions (e.g., environment selection)
    application.add_handler(CallbackQueryHandler(home_selection_callback, pattern="^select_home_"))