"""
=================================================================
This module serves as the core orchestrator for the application. It initializes 
a Flask server that acts as the backbone for a Digital Twin architecture, 
integrating an MQTT client for IoT communication, and a Telegram Bot for user 
interaction via webhooks.
"""

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

# Import environmental constants from the application settings
from src.application.bot.config.settings import (
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

# Telegram Bot Modules
from src.application.bot.routes.webhook_routes import bot_webhook, init_telegram_routes
from src.application.bot.handlers.base_handlers import setup_bot_handlers

# ==============================================================================
# 3. SERVER INITIALIZATION & LIFECYCLE MANAGEMENT
# ==============================================================================

# nest_asyncio is required to allow the Telegram asyncio event loop to run 
# alongside Flask's synchronous/threaded environment without throwing 
# 'Event loop is already running' exceptions.
nest_asyncio.apply()

class FlaskServer:
    """
    Main Server class responsible for bootstrapping the Flask application, 
    injecting dependencies, and managing the lifecycles of the database, 
    MQTT, and Telegram bot services.
    """
    
    def __init__(self):
        """
        Initializes the Flask application, sets up Cross-Origin Resource Sharing (CORS),
        configures JWT authentication, and triggers the initialization of all subsystems.
        """
        self.app = Flask(__name__)
        
        # Enable CORS to allow cross-origin requests from front-end clients
        CORS(self.app)

        # --- JWT CONFIGURATION ---
        # Securing API endpoints using JSON Web Tokens.
        self.app.config['JWT_SECRET_KEY'] = JWT_SECRET_KEY
        self.jwt = JWTManager(self.app)

        # Bootstrap all architectural components
        self._init_components()
        self._init_mqtt()
        self._init_telegram_bot() 
        self._register_blueprints()

    def _init_components(self):
        """
        Initializes the Digital Twin architecture components.
        This includes loading YAML schemas for entities (Room, Pet, User, Door), 
        establishing the database connection, and injecting factories into the 
        Flask app's global configuration for access across different routes.
        """
        # 1. Initialize and populate the Schema Registry
        schema_registry = SchemaRegistry()
        schema_registry.load_schema("room", "src/virtualization/templates/room.yaml")
        schema_registry.load_schema("pet", "src/virtualization/templates/pet.yaml")
        schema_registry.load_schema("user", "src/virtualization/templates/user.yaml")
        schema_registry.load_schema("door", "src/virtualization/templates/door.yaml")
        
        # 2. Database configuration and connection
        db_config = ConfigLoader.load_database_config()
        connection_string = ConfigLoader.build_connection_string(db_config)

        db_service = DatabaseService(
            connection_string=connection_string,
            db_name=db_config["settings"]["name"],
            schema_registry=schema_registry,
        )
        db_service.connect()

        # 3. Initialize the Digital Twin Factory
        dt_factory = DTFactory(db_service, schema_registry)

        # 4. Dependency Injection: Store instances in Flask's config
        self.app.config["SCHEMA_REGISTRY"] = schema_registry
        self.app.config["DB_SERVICE"] = db_service
        self.app.config["DT_FACTORY"] = dt_factory
        
        # Initialize Digital Replica (DR) factories for specific entities
        self.app.config["DR_FACTORY_ROOM"] = DRFactory("src/virtualization/templates/room.yaml")
        self.app.config["DR_FACTORY_PET"]  = DRFactory("src/virtualization/templates/pet.yaml")
        self.app.config["DR_FACTORY_USER"] = DRFactory("src/virtualization/templates/user.yaml")
        self.app.config["DR_FACTORY_DOOR"] = DRFactory("src/virtualization/templates/door.yaml")
        
        # Load the external computer vision model
        self.app.config["PET_DETECTOR"] = PetDetector()

    def _init_mqtt(self):
        """
        Initializes the MQTT manager for IoT message brokering.
        Reads broker credentials from configuration and starts the connection.
        """
        self.mqtt_manager = MQTTManager(self.app)
        self.app.mqtt_manager = self.mqtt_manager
        
        # Load MQTT settings
        mqtt_config = ConfigLoader.load_mqtt_config()
        # (Preserved original duplicated load for exact behavioral match)
        mqtt_config = ConfigLoader.load_mqtt_config() 
        
        # Connect to the MQTT broker
        self.mqtt_manager.start(
            broker=mqtt_config.get("broker"),
            port=mqtt_config.get("port"),
            username=mqtt_config.get("username"),
            password=mqtt_config.get("password")
        )

    def _init_telegram_bot(self):
        """
        Sets up the Telegram Bot asynchronously.
        Uses Ngrok to create a secure tunnel to localhost, enabling Telegram to 
        send updates via Webhooks instead of long-polling. This is crucial for 
        running the bot efficiently alongside a web server.
        """
        # Create a dedicated asyncio event loop for the Telegram application
        self.telegram_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.telegram_loop)

        # Build the Telegram app using the token retrieved from settings.py
        self.telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
        # (Preserved original duplicated builder logic for exact match)
        self.telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # Store bot and loop references in Flask config for external route access
        self.app.config['TELEGRAM_APP'] = self.telegram_app
        self.app.config['TELEGRAM_LOOP'] = self.telegram_loop
        
        # Inject required services into the bot's internal data storage
        self.telegram_app.bot_data["db_service"] = self.app.config["DB_SERVICE"]
        self.telegram_app.bot_data["dt_factory"] = self.app.config["DT_FACTORY"]
        self.telegram_app.bot_data["mqtt_manager"] = self.app.mqtt_manager

        # Register message/command handlers
        setup_bot_handlers(self.telegram_app)

        # Asynchronously initialize and start the Telegram application
        self.telegram_loop.run_until_complete(self.telegram_app.initialize())
        self.telegram_loop.run_until_complete(self.telegram_app.start())

        # Configure Ngrok to expose the local server to the public internet
        ngrok.set_auth_token(NGROK_TOKEN)
        public_url = ngrok.connect(SERVER_PORT).public_url
        webhook_url = f"{public_url}{WEBHOOK_PATH}"
        print(f"[TELEGRAM] Webhook successfully set to: {webhook_url}")

        # Register the generated public URL as the webhook destination for Telegram
        self.telegram_loop.run_until_complete(self.telegram_app.bot.set_webhook(webhook_url))
        
        # Initialize custom routes linking Flask to Telegram
        init_telegram_routes(self.telegram_app, self.telegram_loop)

    def _register_blueprints(self):
        """
        Registers Flask blueprints (modular routing components).
        This separates API logic and Webhook logic into distinct, manageable files.
        """
        register_api_blueprints(self.app)
        self.app.register_blueprint(bot_webhook)

    def run(self, host=SERVER_HOST, port=SERVER_PORT, debug=False):
        """
        Starts the Flask server. 
        Implements a graceful shutdown mechanism via the 'finally' block to 
        ensure databases and connections are properly closed when the server stops.
        
        Args:
            host (str): The IP address to bind to.
            port (int): The port number to listen on.
            debug (bool): Enables Flask debug mode if True.
        """
        try:
            # Start the main WSGI server
            self.app.run(host=host, port=port, debug=debug)
        finally:
            # Graceful shutdown sequence: executed when the server process is interrupted
            print("Shutting down services gracefully...")
            
            # Disconnect from MongoDB/Database
            if "DB_SERVICE" in self.app.config:
                self.app.config["DB_SERVICE"].disconnect()
            
            # Disconnect MQTT client
            if hasattr(self, 'mqtt_manager'):
                self.mqtt_manager.stop()
                
            # Stop the Telegram bot and close the asyncio loop safely
            if hasattr(self, 'telegram_loop'):
                self.telegram_loop.run_until_complete(self.telegram_app.stop())
                self.telegram_loop.close()

if __name__ == "__main__":
    # Entry point of the script
    server = FlaskServer()
    server.run()