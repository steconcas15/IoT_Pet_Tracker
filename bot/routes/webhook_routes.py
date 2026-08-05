from flask import Blueprint, request
from telegram import Update

bot_webhook = Blueprint("bot_webhook", __name__)

# Variabili globali per memorizzare l'app e il loop
telegram_application = None
telegram_loop = None

def init_telegram_routes(app_instance, loop_instance):
    """Salva l'istanza asincrona di Telegram e il loop a livello globale per il blueprint"""
    global telegram_application, telegram_loop
    telegram_application = app_instance
    telegram_loop = loop_instance

@bot_webhook.route("/telegram", methods=["POST"])
def telegram_webhook_handler():
    """Riceve gli update da Telegram e li passa al loop asincrono"""
    if request.method == "POST":
        # Converte il JSON ricevuto in un oggetto Update di Telegram
        update = Update.de_json(request.get_json(), telegram_application.bot)
        
        # Usa il loop salvato globalmente per processare l'update
        telegram_loop.run_until_complete(
            telegram_application.process_update(update)
        )
        return "OK", 200