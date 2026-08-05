import os
from dotenv import load_dotenv

# Carica le variabili d'ambiente dal file .env
load_dotenv()

# Configurazione Bot
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN non trovato nel file .env")

# Configurazione Ngrok
NGROK_TOKEN = os.getenv("NGROK_TOKEN")
if not NGROK_TOKEN:
    raise ValueError("NGROK_TOKEN non trovato nel file .env")

# Configurazione Server e Sicurezza
SERVER_HOST = "0.0.0.0"
SERVER_PORT = int(os.getenv("PORT", 5000))
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "default_secret_key_fallback")

# Configurazione Webhook
WEBHOOK_PATH = "/telegram"