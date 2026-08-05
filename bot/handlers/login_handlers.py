from telegram import Update
from telegram.ext import ContextTypes
from werkzeug.security import check_password_hash

# Dizionario globale (in memoria) per tracciare chi è loggato. 
# Key: telegram_user_id -> Value: database_user_id
LOGGED_USERS = {}

def check_auth(telegram_id):
    """Verifica se un utente Telegram ha effettuato il login."""
    return telegram_id in LOGGED_USERS

async def login_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce il comando /login username password"""
    telegram_id = update.effective_user.id
    
    # Controlla se ci sono abbastanza argomenti
    if len(context.args) < 2:
        await update.message.reply_text("Formato non valido. Usa: /login <username> <password>")
        return

    username = context.args[0]
    password = context.args[1]

    # Recupera il DB_SERVICE che abbiamo passato in app.py
    db_service = context.bot_data.get("db_service")
    if not db_service:
        await update.message.reply_text("Errore interno: Database non connesso.")
        return

    try:
        # Cerca l'utente nel DB (usando lo stesso metodo che hai nelle API)
        user = db_service.get_user_by_username(username)

        # Verifica esistenza e validità password
        if not user or not check_password_hash(user['profile']['password'], password):
            await update.message.reply_text("Credenziali non valide. Riprova.")
            return

        # Login effettuato con successo: Salva la sessione
        user_id_str = str(user['_id'])
        LOGGED_USERS[telegram_id] = user_id_str

        await update.message.reply_text(f"Login completato! Benvenuto {username}. Sei ora collegato al tuo Digital Twin.")

    except Exception as e:
        await update.message.reply_text(f"Errore durante il login: {str(e)}")

async def logout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rimuove la sessione dell'utente"""
    telegram_id = update.effective_user.id
    
    if telegram_id in LOGGED_USERS:
        del LOGGED_USERS[telegram_id]
        await update.message.reply_text("Disconnesso con successo dal Digital Twin.")
    else:
        await update.message.reply_text("Non sei attualmente loggato.")