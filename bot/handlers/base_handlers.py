from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes, CommandHandler, MessageHandler, filters
from bot.handlers.login_handlers import login_handler, logout_handler
from bot.handlers.pet_handlers import locate_handler, buzzer_handler
from bot.handlers.login_handlers import home_selection_callback

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Risponde al comando /start"""
    welcome_message = (
        "🐾 Benvenuto nell'IoT Pet Tracker Bot!\n\n"
        "Per iniziare, devi collegare il tuo account.\n"
        "Usa il comando: /login <username> <password>"
    )
    await update.message.reply_text(welcome_message)

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Risponde al comando /help"""
    help_text = (
        "🤖 Guida ai comandi:\n"
        "/start - Avvia il bot\n"
        "/login <user> <pass> - Accedi al sistema\n"
        "/logout - Esci dal sistema\n"
        "/locate - (In arrivo) Trova il pet\n"
        "/buzzer - (In arrivo) Suona l'allarme\n"
    )
    await update.message.reply_text(help_text)

async def echo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Risponde ai messaggi non riconosciuti"""
    await update.message.reply_text("Comando non riconosciuto. Scrivi /help per la lista dei comandi.")

def setup_bot_handlers(application):
    """Registra tutti gli handler sull'applicazione Telegram"""
    
    # Comandi di base
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("help", help_handler))
    
    # Autenticazione
    application.add_handler(CommandHandler("login", login_handler))
    application.add_handler(CommandHandler("logout", logout_handler))
    
    # Azioni IoT Pet Tracker
    application.add_handler(CommandHandler("locate", locate_handler))
    application.add_handler(CommandHandler("buzzer", buzzer_handler))
    
    # Filtro di fallback (deve restare l'ultimo della lista)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo_handler))
    application.add_handler(CallbackQueryHandler(home_selection_callback, pattern="^select_home_"))