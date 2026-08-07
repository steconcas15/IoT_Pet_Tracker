from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from werkzeug.security import check_password_hash

# Struttura aggiornata: telegram_user_id -> {"user_id": string, "home_id": string}
LOGGED_USERS = {}

def check_auth(telegram_id):
    """Verifica se un utente Telegram ha effettuato il login."""
    return telegram_id in LOGGED_USERS

async def login_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce il comando /login username password e cancella il messaggio per privacy"""
    telegram_id = update.effective_user.id
    
    # 1. ELIMINAZIONE IMMEDIATA DEL MESSAGGIO
    # Il bot tenta di cancellare il messaggio dell'utente (che contiene la password)
    try:
        if update.message:
            await update.message.delete()
    except Exception as e:
        print(f"[SECURITY WARNING] Impossibile cancellare il messaggio di login: {e}")
        # Se fallisce (es. permessi mancanti in un gruppo), avvisiamo l'utente
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="⚠️ **Attenzione di Sicurezza:** Non ho i permessi per cancellare il tuo messaggio. Elimina tu stesso il messaggio con la password per proteggere il tuo account!",
            parse_mode='Markdown'
        )
    
    # FIX: Controllo se l'utente è già loggato
    if check_auth(telegram_id):
        await update.message.reply_text("⚠️ Sei già loggato! Usa /logout prima di accedere con un altro account.")
        return

    # Controlla se ci sono abbastanza argomenti
    if len(context.args) < 2:
        await update.message.reply_text("Formato non valido. Usa: /login <username> <password>")
        return

    username = context.args[0]
    password = context.args[1]

    # Recupera il DB_SERVICE
    db_service = context.bot_data.get("db_service")
    if not db_service:
        await update.message.reply_text("Errore interno: Database non connesso.")
        return

    try:
        user = db_service.get_user_by_username(username)

        # Verifica esistenza e validità password
        if not user or not check_password_hash(user['profile']['password'], password):
            await update.message.reply_text("Credenziali non valide. Riprova.")
            return

        user_id_str = str(user['_id'])
        
        # Recupera tutte le case (admin e viewer)
        owned_homes = user.get("data", {}).get("owned_homes", [])
        viewable_homes = user.get("data", {}).get("viewable_homes", [])
        all_homes = owned_homes + viewable_homes

        if not all_homes:
            LOGGED_USERS[telegram_id] = {"user_id": user_id_str, "home_id": None}
            await update.message.reply_text(f"Login completato, {username}. Tuttavia, non hai nessuna casa associata.")
            return

        # Se l'utente ha una sola casa, selezionala automaticamente
        if len(all_homes) == 1:
            LOGGED_USERS[telegram_id] = {"user_id": user_id_str, "home_id": all_homes[0]}
            await update.message.reply_text(f"Login completato! Benvenuto {username}. Casa selezionata automaticamente.")
            return

        # Se ci sono più case, genera una tastiera per la selezione
        keyboard = []
        dt_factory = context.bot_data.get("dt_factory")
        
        for home_id in all_homes:
            dt = dt_factory.get_dt(home_id) if dt_factory else None
            home_name = dt.get("name", home_id) if dt else home_id
            ruolo = "Admin" if home_id in owned_homes else "Viewer"
            
            keyboard.append([InlineKeyboardButton(f"{home_name} ({ruolo})", callback_data=f"select_home_{home_id}")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Salva temporaneamente l'user_id per completare il login dopo il click
        context.user_data['pending_login_user_id'] = user_id_str
        
        await update.message.reply_text(
            f"Benvenuto {username}! Hai accesso a più case.\nSeleziona quale vuoi gestire in questa sessione:",
            reply_markup=reply_markup
        )

    except Exception as e:
        await update.message.reply_text(f"Errore durante il login: {str(e)}")


async def home_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce il click sui bottoni di selezione della casa"""
    query = update.callback_query
    await query.answer()
    
    telegram_id = update.effective_user.id
    data = query.data
    
    if data.startswith("select_home_"):
        home_id = data.replace("select_home_", "")
        user_id_str = context.user_data.get('pending_login_user_id')
        
        if not user_id_str:
            await query.edit_message_text("Sessione di login scaduta o non valida. Rifai il /login.")
            return
        
        # Registra l'utente loggato con la casa scelta
        LOGGED_USERS[telegram_id] = {"user_id": user_id_str, "home_id": home_id}
        del context.user_data['pending_login_user_id']
        
        await query.edit_message_text("Casa selezionata con successo! Sei ora collegato al Digital Twin scelto.")


async def logout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rimuove la sessione dell'utente"""
    telegram_id = update.effective_user.id
    
    if telegram_id in LOGGED_USERS:
        del LOGGED_USERS[telegram_id]
        await update.message.reply_text("Disconnesso con successo dal Digital Twin.")
    else:
        await update.message.reply_text("Non sei attualmente loggato.")