import requests
from flask import current_app
from bot.handlers.login_handlers import LOGGED_USERS
from bot.config.settings import TELEGRAM_TOKEN

def send_unauthorized_room_alert(room_name):
    """
    Invia un alert di intrusione immediato tramite una richiesta HTTP POST 
    diretta alle API di Telegram, slegata dai vincoli dei loop asincroni.
    """
    if not TELEGRAM_TOKEN:
        print("[TELEGRAM] Token non configurato per l'invio diretto.")
        return

    alert_text = (
        f"🚨 **ALLARME INTRUSIONE!** 🚨\n\n"
        f"Il tuo pet è appena stato rilevato in **{room_name}**, "
        f"una stanza in cui non è autorizzato a entrare!"
    )
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    # Invia il messaggio a tutti gli utenti loggati tramite una chiamata HTTP standard
    for chat_id in LOGGED_USERS.keys():
        payload = {
            "chat_id": chat_id,
            "text": alert_text,
            "parse_mode": "Markdown"
        }
        try:
            response = requests.post(url, json=payload, timeout=3)
            if response.status_code == 200:
                print(f"[TELEGRAM] Alert HTTP inviato con successo all'utente {chat_id}")
            else:
                print(f"[TELEGRAM] Errore API Telegram ({response.status_code}): {response.text}")
        except Exception as e:
            print(f"[TELEGRAM] Errore di rete durante l'invio dell'alert: {e}")


def send_otp_to_telegram(user_id, otp_code):
    """
    Invia il codice OTP direttamente alla chat Telegram dell'utente 
    tramite una richiesta HTTP POST, senza richiedere comandi in entrata.
    """
    if not TELEGRAM_TOKEN:
        print("[TELEGRAM] Token non configurato per l'invio diretto.")
        return False

    # Trova il telegram_id corrispondente al database user_id
    target_chat_id = None
    for t_id, db_u_id in LOGGED_USERS.items():
        if str(db_u_id) == str(user_id):
            target_chat_id = t_id
            break

    if not target_chat_id:
        print(f"[TELEGRAM] Nessuna chat Telegram attiva trovata per l'utente {user_id}. Effettua prima il /login.")
        return False

    message_text = (
        f"🔐 **Codice di Verifica OTP** 🔐\n\n"
        f"Il tuo codice temporaneo è: `{otp_code}`\n"
        f"Scadrà tra 5 minuti. Inseriscilo nell'interfaccia web per confermare l'operazione."
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
            print(f"[TELEGRAM] OTP inviato con successo all'utente {target_chat_id}")
            return True
        else:
            print(f"[TELEGRAM] Errore API Telegram ({response.status_code}): {response.text}")
            return False
    except Exception as e:
        print(f"[TELEGRAM] Errore di rete durante l'invio dell'OTP: {e}")
        return False