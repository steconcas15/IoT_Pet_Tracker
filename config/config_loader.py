"""
Configuration Management Module
===============================
This module provides a centralized utility for securely loading, parsing, and 
validating system configuration parameters from external YAML files. It isolates 
environment-specific configurations (like database URIs and MQTT credentials) 
from the core application logic.
"""

import yaml
from typing import Dict
import os

# ==============================================================================
# The @staticmethod decorator is utilized to define methods bound to the class 
# namespace rather than an instance. This allows the ConfigLoader to act as a 
# stateless utility namespace without requiring class instantiation.
# ==============================================================================

class ConfigLoader:
    """
    A stateless utility class engineered to handle the deserialization, 
    validation, and structured parsing of infrastructure configuration 
    settings (e.g., Database, MQTT) from external YAML files.
    """
    
    @staticmethod
    def load_database_config(config_path: str = "config/database.yaml") -> Dict:
        """
        Loads and validates the database configuration block from a specified YAML file.

        Args:
            config_path (str): The relative or absolute path to the configuration file.

        Returns:
            Dict: A validated dictionary containing database configuration parameters.

        Raises:
            FileNotFoundError: If the specified configuration file is inaccessible or missing.
            ValueError: If the file is malformed or lacks the critical 'database' root node.
        """
        # 1. Verify the physical existence of the configuration file on the filesystem
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        # 2. Open the file stream and safely parse the YAML content
        with open(config_path, "r") as f:
            # yaml.safe_load is strictly used to prevent arbitrary code execution vulnerabilities
            config = yaml.safe_load(f)

        # 3. Enforce structural integrity: ensure the file contains the required "database" namespace
        if not config or "database" not in config:
            raise ValueError("Invalid configuration file: missing root 'database' section.")

        # Extract and return only the isolated database configuration dictionary
        return config["database"]

    
    @staticmethod
    def build_connection_string(config: Dict) -> str:
        """
        Constructs a standard MongoDB connection URI string based on parsed configuration parameters.
        
        Args:
            config (Dict): The database configuration dictionary containing network and auth parameters.
            
        Returns:
            str: A fully qualified MongoDB connection string (e.g., "mongodb://user:pass@host:port").
        """
        conn = config["connection"]
        host = conn["host"]
        port = conn["port"]

        # Initialize the authentication string block
        auth = ""

        # Dynamically inject credentials if both username and password are provided
        if conn.get("username") and conn.get("password"):
            # Format the credentials adhering to the standard URI specification: "username:password@"
            auth = f"{conn['username']}:{conn['password']}@"

        # Concatenate and return the fully qualified MongoDB URI string
        return f"mongodb://{auth}{host}:{port}"
    

    @staticmethod
    def load_mqtt_config(file_path: str = "config/mqtt_config.yaml") -> Dict:
        """
        Parses and extracts the MQTT broker network settings and credentials from a YAML file.
        
        Args:
            file_path (str): The path to the MQTT configuration file.
            
        Returns:
            Dict: A dictionary containing the target MQTT parameters.
            
        Raises:
            FileNotFoundError: If the designated MQTT configuration file is absent.
        """
        # Verify the file's presence on the disk prior to opening the stream
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"MQTT configuration file not found: {file_path}")
        
        # Safely deserialize the YAML content and extract the specific 'mqtt' node
        with open(file_path, "r") as file:
            config = yaml.safe_load(file)
            return config.get("mqtt", {})