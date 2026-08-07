# ==============================================================================
# 1. CORE DEPENDENCIES & PACKAGES
# ==============================================================================
import asyncio
import nest_asyncio
from pyngrok import ngrok
from telegram.ext import Application
from flask import Flask  
from flask_cors import CORS
from flask_jwt_extended import JWTManager

# Importiamo le costanti ambientali dal nuovo file settings.py
from bot.config.settings import (
    TELEGRAM_TOKEN, 
    NGROK_TOKEN, 
    SERVER_PORT, 
    SERVER_HOST, 
    WEBHOOK_PATH, 
    JWT_SECRET_KEY
)

# ==============================================================================
# 2. INTERNAL MODULES & SERVICES (Digital Twin Stack)
# ==============================================================================
from src.virtualization.digital_replica.schema_registry import SchemaRegistry
from src.services.database_service import DatabaseService
from src.virtualization.digital_replica.dr_factory import DRFactory
from src.digital_twin.dt_factory import DTFactory
from src.application.api import register_api_blueprints
from config.config_loader import ConfigLoader
from src.services.mqtt_service import MQTTManager
from vision_model.model import PetDetector

# Moduli del Bot Telegram
from bot.routes.webhook_routes import bot_webhook, init_telegram_routes
from bot.handlers.base_handlers import setup_bot_handlers

# ==============================================================================
# 3. SERVER INITIALIZATION & LIFECYCLE MANAGEMENT
# ==============================================================================

nest_asyncio.apply()

class FlaskServer:
    def __init__(self):
        self.app = Flask(__name__)
        CORS(self.app)

        # --- CONFIGURAZIONE JWT tramite .env ---
        self.app.config['JWT_SECRET_KEY'] = JWT_SECRET_KEY
        self.jwt = JWTManager(self.app)

        self._init_components()
        self._init_mqtt()
        self._init_telegram_bot() 
        self._register_blueprints()

    def _init_components(self):
        """Initialize all required components and store them in app config"""
        schema_registry = SchemaRegistry()
        schema_registry.load_schema("room", "src/virtualization/templates/room.yaml")
        schema_registry.load_schema("pet", "src/virtualization/templates/pet.yaml")
        schema_registry.load_schema("user", "src/virtualization/templates/user.yaml")
        schema_registry.load_schema("door", "src/virtualization/templates/door.yaml")
        
        db_config = ConfigLoader.load_database_config()
        connection_string = ConfigLoader.build_connection_string(db_config)

        db_service = DatabaseService(
            connection_string=connection_string,
            db_name=db_config["settings"]["name"],
            schema_registry=schema_registry,
        )
        db_service.connect()

        dt_factory = DTFactory(db_service, schema_registry)

        self.app.config["SCHEMA_REGISTRY"] = schema_registry
        self.app.config["DB_SERVICE"] = db_service
        self.app.config["DT_FACTORY"] = dt_factory
        
        self.app.config["DR_FACTORY_ROOM"] = DRFactory("src/virtualization/templates/room.yaml")
        self.app.config["DR_FACTORY_PET"]  = DRFactory("src/virtualization/templates/pet.yaml")
        self.app.config["DR_FACTORY_USER"] = DRFactory("src/virtualization/templates/user.yaml")
        self.app.config["DR_FACTORY_DOOR"] = DRFactory("src/virtualization/templates/door.yaml")
        self.app.config["PET_DETECTOR"] = PetDetector()

    def _init_mqtt(self):
        """Inizializza il gestore MQTT delegando la logica al servizio esterno"""
        self.mqtt_manager = MQTTManager(self.app)
        self.app.mqtt_manager = self.mqtt_manager
        
        mqtt_config = ConfigLoader.load_mqtt_config()
        mqtt_config = ConfigLoader.load_mqtt_config()
        self.mqtt_manager.start(
            broker=mqtt_config.get("broker"),
            port=mqtt_config.get("port"),
            username=mqtt_config.get("username"),
            password=mqtt_config.get("password")
        )

    def _init_telegram_bot(self):
        """Inizializza il loop asincrono, il bot Telegram e Ngrok usando le variabili d'ambiente"""
        
        self.telegram_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.telegram_loop)

        self.telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # Costruisce l'app Telegram usando il token prelevato dal file settings.py
        self.telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # AGGIUNGI QUESTE DUE RIGHE: Salviamo bot e loop in Flask config
        self.app.config['TELEGRAM_APP'] = self.telegram_app
        self.app.config['TELEGRAM_LOOP'] = self.telegram_loop
        
        self.telegram_app.bot_data["db_service"] = self.app.config["DB_SERVICE"]
        self.telegram_app.bot_data["dt_factory"] = self.app.config["DT_FACTORY"]
        self.telegram_app.bot_data["mqtt_manager"] = self.app.mqtt_manager

        setup_bot_handlers(self.telegram_app)

        self.telegram_loop.run_until_complete(self.telegram_app.initialize())
        self.telegram_loop.run_until_complete(self.telegram_app.start())

        ngrok.set_auth_token(NGROK_TOKEN)
        public_url = ngrok.connect(SERVER_PORT).public_url
        webhook_url = f"{public_url}{WEBHOOK_PATH}"
        print(f"[TELEGRAM] Webhook impostato su: {webhook_url}")

        self.telegram_loop.run_until_complete(self.telegram_app.bot.set_webhook(webhook_url))
        
        # AGGIORNA QUESTA RIGA PASSANDO ANCHE IL LOOP:
        init_telegram_routes(self.telegram_app, self.telegram_loop)


    def _register_blueprints(self):
        """Register all API blueprints"""
        register_api_blueprints(self.app)
        self.app.register_blueprint(bot_webhook)

    def run(self, host=SERVER_HOST, port=SERVER_PORT, debug=False):
        """Run the Flask server usando i parametri ambientali"""
        try:
            self.app.run(host=host, port=port, debug=debug)
        finally:
            print("Shutting down services...")
            if "DB_SERVICE" in self.app.config:
                self.app.config["DB_SERVICE"].disconnect()
            
            if hasattr(self, 'mqtt_manager'):
                self.mqtt_manager.stop()
                
            if hasattr(self, 'telegram_loop'):
                self.telegram_loop.run_until_complete(self.telegram_app.stop())
                self.telegram_loop.close()

if __name__ == "__main__":
    server = FlaskServer()
    server.run()