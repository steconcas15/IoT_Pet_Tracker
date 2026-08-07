import requests
from flask import current_app
from bot.handlers.login_handlers import LOGGED_USERS
from bot.config.settings import TELEGRAM_TOKEN

# Dizionario per tracciare gli allarmi inviati. Formato: home_id -> [(chat_id, message_id), ...]
ACTIVE_OFFLINE_ALERTS = {}

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
    for t_id, user_data in LOGGED_USERS.items():
        if str(user_data["user_id"]) == str(user_id):
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

def send_offline_alert(home_id, offline_devices, all_offline):
    """
    Invia un alert tramite HTTP diretto a chi è loggato nella casa
    quando il timer MQTT rileva dispositivi OFFLINE.
    """
    from bot.handlers.login_handlers import LOGGED_USERS
    from bot.config.settings import TELEGRAM_TOKEN
    import requests

    if not TELEGRAM_TOKEN:
        return

    # Inizializza la lista per questa casa se non esiste
    if home_id not in ACTIVE_OFFLINE_ALERTS:
        ACTIVE_OFFLINE_ALERTS[home_id] = []

    if all_offline:
        alert_text = (
            "🔌 **ALLARME CONNESSIONE** 🔌\n\n"
            "Tutti i dispositivi della casa risultano **OFFLINE**.\n"
            "C'è stato un problema al router/Wi-Fi o è saltata la corrente!"
        )
    else:
        safe_devices = [str(d).replace("_", "\\_").replace("*", "") for d in offline_devices]
        devices_list = "\n".join([f"• {d}" for d in safe_devices])
        alert_text = (
            "⚠️ **ATTENZIONE: Dispositivi Offline** ⚠️\n\n"
            "I seguenti dispositivi hanno perso la connessione:\n"
            f"{devices_list}"
        )

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

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
                    print(f"[TELEGRAM] Alert Offline inviato all'utente {chat_id}")
                    # SALVATAGGIO ID MESSAGGIO PER POTERLO ELIMINARE DOPO
                    data = response.json()
                    msg_id = data.get("result", {}).get("message_id")
                    if msg_id:
                        ACTIVE_OFFLINE_ALERTS[home_id].append((chat_id, msg_id))
                else:
                    print(f"[TELEGRAM ERROR] Impossibile inviare alert. Codice {response.status_code}: {response.text}")
            except Exception as e:
                print(f"[TELEGRAM] Errore di rete durante l'invio dell'alert offline: {e}")


def send_online_recovery(home_id):
    """
    Elimina i messaggi di allerta precedenti e invia un avviso 
    di situazione ristabilita quando tutti i dispositivi tornano online.
    """
    from bot.handlers.login_handlers import LOGGED_USERS
    from bot.config.settings import TELEGRAM_TOKEN
    import requests

    if not TELEGRAM_TOKEN:
        return

    # Controlla se c'erano allarmi attivi per questa casa
    alerts = ACTIVE_OFFLINE_ALERTS.get(home_id, [])
    if not alerts:
        return  # Nessun allarme da cancellare, esce silenziosamente

    # 1. ELIMINA I MESSAGGI DI ERRORE PRECEDENTI
    delete_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteMessage"
    for chat_id, msg_id in alerts:
        try:
            requests.post(delete_url, json={"chat_id": chat_id, "message_id": msg_id}, timeout=3)
        except Exception as e:
            print(f"[TELEGRAM] Errore eliminazione vecchio alert: {e}")

    # 2. INVIA IL MESSAGGIO "SITUAZIONE RISTABILITA"
    alert_text = (
        "✅ **SITUAZIONE RISTABILITA** ✅\n\n"
        "Tutti i dispositivi della casa sono tornati regolarmente **ONLINE**."
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
                pass

    # Resetta la lista degli allarmi per questa casa
    ACTIVE_OFFLINE_ALERTS[home_id] = []