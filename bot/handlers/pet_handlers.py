from telegram import Update
from telegram.ext import ContextTypes
from datetime import datetime, timezone
from bot.handlers.login_handlers import LOGGED_USERS

async def locate_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce il comando /locate per trovare la stanza attuale del pet"""
    telegram_id = update.effective_user.id
    if telegram_id not in LOGGED_USERS:
        await update.message.reply_text("⚠️ Devi prima effettuare il /login.")
        return

    # Estrazione dell'id utente e della casa selezionata dalla nuova struttura
    user_data = LOGGED_USERS[telegram_id]
    user_id = user_data["user_id"]
    home_id = user_data["home_id"]

    if not home_id:
        await update.message.reply_text("Non hai nessuna casa selezionata. Effettua nuovamente il /login per sceglierne una.")
        return

    db_service = context.bot_data["db_service"]
    dt_factory = context.bot_data["dt_factory"]

    try:
        # Usa la casa selezionata durante il login
        dt_data = dt_factory.get_dt(home_id)
        
        if not dt_data:
            await update.message.reply_text("Errore: Impossibile trovare la casa selezionata.")
            return
            
        # Cerca la replica del pet all'interno della casa
        pet_dr = None
        for replica in dt_data.get("digital_replicas", []):
            if replica.get("type") == "pet":
                pet_dr = db_service.get_dr("pet", replica.get("id"))
                break
        
        if not pet_dr:
            await update.message.reply_text("Non ho trovato nessun pet associato al tuo ambiente.")
            return

        pet_name = pet_dr.get("profile", {}).get("name", "Il tuo pet")
        current_room = pet_dr.get("data", {}).get("current_room", "sconosciuta")
        
        await update.message.reply_text(f"📍 **{pet_name}** si trova attualmente in: **{current_room}**", parse_mode='Markdown')

    except Exception as e:
        await update.message.reply_text(f"Errore durante la localizzazione: {str(e)}")


async def buzzer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce il comando /buzzer consentendolo solo se il pet è in una stanza consentita (allowed) e l'utente è admin"""
    telegram_id = update.effective_user.id
    if telegram_id not in LOGGED_USERS:
        await update.message.reply_text("⚠️ Devi prima effettuare il /login.")
        return

    # Estrazione dell'id utente e della casa selezionata dalla nuova struttura
    user_data = LOGGED_USERS[telegram_id]
    user_id = user_data["user_id"]
    home_id = user_data["home_id"]

    if not home_id:
        await update.message.reply_text("Non hai nessuna casa selezionata. Effettua nuovamente il /login per sceglierne una.")
        return

    db_service = context.bot_data["db_service"]
    dt_factory = context.bot_data["dt_factory"]
    mqtt_manager = context.bot_data["mqtt_manager"]

    try:
        # BLOCCO DI SICUREZZA: Verifica se l'utente è admin della casa selezionata
        user = db_service.get_user_by_id(user_id)
        if not user:
            await update.message.reply_text("Errore: Utente non trovato nel database.")
            return
            
        owned_homes = user.get("data", {}).get("owned_homes", [])
        if home_id not in owned_homes:
            await update.message.reply_text("⛔ Operazione negata: Solo l'amministratore della casa può usare il comando /buzzer.")
            return

        # Usa direttamente l'home_id della sessione
        dt_data = dt_factory.get_dt(home_id)
        
        if not dt_data:
            await update.message.reply_text("Errore: Impossibile trovare la casa selezionata.")
            return

        pet_id = None
        pet_name = "Il tuo pet"
        pet_dr = None
        
        # Recuperiamo la replica digitale del pet
        for replica in dt_data.get("digital_replicas", []):
            if replica.get("type") == "pet":
                pet_id = replica.get("id")
                pet_dr = db_service.get_dr("pet", pet_id)
                if pet_dr:
                    pet_name = pet_dr.get("profile", {}).get("name", pet_name)
                break
        
        if not pet_dr or not pet_id:
            await update.message.reply_text("Nessun pet trovato nella casa attuale.")
            return

        # 1. Recuperiamo la stanza attuale del pet e verifichiamo i permessi
        current_room_name = pet_dr.get("data", {}).get("current_room")
        
        if not current_room_name:
            await update.message.reply_text("⚠️ Non riesco a determinare la stanza attuale del pet.")
            return

        rooms = db_service.query_drs("room", {"profile.name": current_room_name})
        if rooms:
            permission_level = rooms[0].get("profile", {}).get("permission_level", "allowed")
            
            # BLOCCO DI SICUREZZA: Se la stanza è vietata, l'utente non può comandare il buzzer manualmente
            if permission_level == "forbidden":
                await update.message.reply_text(
                    f"⛔ Comando non consentito! {pet_name} si trova in **{current_room_name}** "
                    f"(stanza vietata). Il buzzer è gestito automaticamente dal sistema di sicurezza.",
                    parse_mode='Markdown'
                )
                return

        # 2. Controlla lo stato attuale del buzzer nel database (Logica Toggle)
        current_status = pet_dr.get("data", {}).get("buzzer_status", "OFF")

        if current_status == "ON":
            # Spegnimento manuale da parte dell'utente
            mqtt_manager.client.publish("casa/sound", "OFF")
            
            db_service.update_dr(dr_type="pet", dr_id=pet_id, update_data={
                "data.buzzer_status": "OFF"
            })
            
            await update.message.reply_text(f"🔇 **Buzzer spento** manualmente per {pet_name}.", parse_mode='Markdown')
            
        else:
            # Accensione manuale consentita
            mqtt_manager.client.publish("casa/sound", "ON")
            
            db_service.update_dr(dr_type="pet", dr_id=pet_id, update_data={
                "data.buzzer_status": "ON",
                "data.last_buzzer_start_time": datetime.now(timezone.utc).isoformat()
            })

            # Messaggio aggiornato con le istruzioni di spegnimento
            await update.message.reply_text(
                f"🔊 **Buzzer azionato** manualmente per {pet_name} in stanza sicura!\n"
                f"Rifai il comando /buzzer per disattivarlo.", 
                parse_mode='Markdown'
            )

    except Exception as e:
        await update.message.reply_text(f"Errore durante l'interazione con il buzzer: {str(e)}")