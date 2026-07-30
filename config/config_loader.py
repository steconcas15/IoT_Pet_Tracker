import yaml
from typing import Dict
import os

# @staticmethod is a decorator used to define a method inside a class that does not need access to the class or instance state



class ConfigLoader:

    """
    A utility class to handle loading, validating, and parsing 
    database configuration settings from YAML files.
    """
    
    @staticmethod
    def load_database_config(config_path: str = "config/database.yaml") -> Dict:
        
        """Load database configuration from YAML file"""

        # 1. Check if the configuration file physically exists on the disk
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        # 2. Open and safely parse the YAML file
        with open(config_path, "r") as f:
            # safe_load prevents execution of arbitrary code inside the YAML file
            config = yaml.safe_load(f)

        # 3. Validate that the file is not empty and contains the required top-level "database" key
        if not config or "database" not in config:
            raise ValueError("Invalid configuration file: missing database section")

        # Return only the sub-dictionary under the "database" key
        return config["database"]

    
    @staticmethod
    def build_connection_string(config: Dict) -> str:
        
        """Build MongoDB connection string from configuration"""
        
        conn = config["connection"]
        host = conn["host"]
        port = conn["port"]

        # Build authentication part if credentials are provided
        auth = ""

        # Check if both 'username' and 'password' are provided and are not empty/None
        if conn.get("username") and conn.get("password"):
            # Format the credentials matching the MongoDB URI standard: "username:password@"
            auth = f"{conn['username']}:{conn['password']}@"

        # Assemble and return the complete MongoDB connection URI (in our case it returns "mongodb://localhost:27017")
        return f"mongodb://{auth}{host}:{port}"
    

    @staticmethod
    def load_mqtt_config(file_path="config/mqtt_config.yaml"):
        """Carica le credenziali e le impostazioni MQTT dal file YAML."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File di configurazione MQTT non trovato: {file_path}")
        
        with open(file_path, "r") as file:
            config = yaml.safe_load(file)
            return config.get("mqtt", {})
