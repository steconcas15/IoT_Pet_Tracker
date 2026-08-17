import os
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

# Bot Configuration
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN not found in the .env file")

# Ngrok Configuration
NGROK_TOKEN = os.getenv("NGROK_TOKEN")
if not NGROK_TOKEN:
    raise ValueError("NGROK_TOKEN not found in the .env file")

# Server and Security Configuration
SERVER_HOST = "0.0.0.0"
SERVER_PORT = int(os.getenv("PORT", 5000))
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "default_secret_key_fallback")

# Webhook Configuration
WEBHOOK_PATH = "/telegram"