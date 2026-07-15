# ==============================================================================
# 1. CORE DEPENDENCIES & PACKAGES
# ==============================================================================

# Pulling in Flask to spin up our web server.
from flask import Flask  # Pulling in Flask to spin up our web server.

# CORS is a must-have so our frontend (like React) can talk to this API.
from flask_cors import CORS

# ==============================================================================
# 2. INTERNAL MODULES & SERVICES (Digital Twin Stack)
# ==============================================================================

# Tracks and validates data structures/blueprints for our digital replicas
from src.virtualization.digital_replica.schema_registry import SchemaRegistry

# The heavy lifter for database interactions (queries, connections, etc.).
from src.services.database_service import DatabaseService

# Factory pattern handler to dynamically build out Digital Twin instances.
from src.digital_twin.dt_factory import DTFactory

# Links and registers all our API routes/endpoints in one go.
from src.application.api import register_api_blueprints

# Quick utility to grab credentials and settings from config files.
from config.config_loader import ConfigLoader

# ==============================================================================
# 3. SERVER INITIALIZATION & LIFECYCLE MANAGEMENT
# ==============================================================================

class FlaskServer:
    def __init__(self):
        self.app = Flask(__name__)
        CORS(self.app)
        self._init_components()
        self._register_blueprints()

    def _init_components(self):
        """Initialize all required components and store them in app config"""

        # 1 - Spins up the central schema manager. It will load, compile, and cache our YAML blueprints into MongoDB-compatible rules.
        schema_registry = SchemaRegistry()
        
        # 2.0 - Load the database configuration settings from the YAML file (db_config will contain a dictionary of your YAML database settings)
        db_config = ConfigLoader.load_database_config()

        # 2.1 - Dynamically build the final MongoDB connection URI using the loaded config (connection_string <- "mongodb://localhost:27017")
        connection_string = ConfigLoader.build_connection_string(db_config)

        # 2.2 - Initialize DatabaseService with populated schema_registry
        db_service = DatabaseService(
            connection_string=connection_string,
            db_name=db_config["settings"]["name"],
            schema_registry=schema_registry,
        )

        # 2.3 - Open the physical pipe (tubo) to the database.
        db_service.connect()

        # 3- Hand over the DB and schemas to the factory to forge our Digital Twins.
        dt_factory = DTFactory(db_service, schema_registry)

        # Store references
        self.app.config["SCHEMA_REGISTRY"] = schema_registry
        self.app.config["DB_SERVICE"] = db_service
        self.app.config["DT_FACTORY"] = dt_factory

    def _register_blueprints(self):
        """Register all API blueprints"""
        register_api_blueprints(self.app)

    def run(self, host="0.0.0.0", port=5000, debug=True):
        """Run the Flask server"""
        try:
            self.app.run(host=host, port=port, debug=debug)
        finally:
            # Cleanup on server shutdown
            if "DB_SERVICE" in self.app.config:
                self.app.config["DB_SERVICE"].disconnect()


if __name__ == "__main__":
    server = FlaskServer()
    server.run()
