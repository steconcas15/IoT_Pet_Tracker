"""
Schema Registry & Validation Translation Module
=============================================
This module acts as the central authoritative registry for structural data schemas 
within the Digital Twin architecture. It is responsible for ingesting human-readable 
YAML entity definitions and compiling them into native MongoDB `$jsonSchema` structures, 
thereby enforcing strict database-level validation and referential integrity.
"""

from typing import Dict, Any
import yaml

# ==============================================================================
# SCHEMA REGISTRY COMPONENT
# ==============================================================================

class SchemaRegistry:
    """
    A registry singleton-like class designed to parse, translate, and cache 
    validation schemas. It bridges the gap between application-level YAML 
    configurations and MongoDB's BSON validation engine.
    """

    def __init__(self):
        """
        Initializes the schema registry context.
        Allocates an empty dictionary to hold all compiled MongoDB schemas, 
        indexed by their respective Digital Replica type strings.
        """
        self.schemas = {}

    # --------------------------------------------------------------------------
    # YAML PARSING & COMPILATION PIPELINE
    # --------------------------------------------------------------------------
    
    def load_schema(self, schema_type: str, yaml_path: str) -> None:
        """
        Loads a schema definition from a local YAML file and triggers its 
        compilation into a MongoDB-compatible JSON schema.

        Args:
            schema_type (str): The classification identifier for the schema (e.g., 'room', 'pet').
            yaml_path (str): The absolute or relative file path to the YAML definition.

        Raises:
            ValueError: If the file is inaccessible, improperly formatted, or missing the 'schemas' root node.
        """
        try:
            # Open the designated YAML file in read-only mode to prevent accidental mutations
            with open(yaml_path, "r") as file:
                # Safely parse the raw YAML syntax into a navigable Python dictionary
                raw_schema = yaml.safe_load(file)

            # Structural sanity check: verify the existence of the expected root namespace
            if not raw_schema or "schemas" not in raw_schema:
                raise ValueError(f"Invalid schema structure detected in {yaml_path}")

            # ┌────────────────────────────────────────────────────────────────┐
            # │                     CONVERSION PIPELINE                        │
            # ├────────────────────────────────────────────────────────────────┤
            # │ Isolate the "schemas" block from the YAML structure and pass   │
            # │ it to the internal translation engine for BSON mapping.        │
            # └────────────────────────────────────────────────────────────────┘
            validation_schema = self._convert_yaml_to_mongodb_schema(
                raw_schema["schemas"]
            )

            # Persist the fully compiled MongoDB schema into the memory cache
            self.schemas[schema_type] = validation_schema

        except Exception as e:
            # Global exception handler for file I/O errors and parsing failures
            raise ValueError(f"Failed to load schema from {yaml_path}: {str(e)}")

    # --------------------------------------------------------------------------
    # TRANSLATION ENGINE (YAML -> MONGODB BSON)
    # --------------------------------------------------------------------------
    def _convert_yaml_to_mongodb_schema(self, yaml_schema: Dict) -> Dict:
        """
        Translates abstract YAML schema definitions into strict MongoDB `$jsonSchema` formats.

        Args:
            yaml_schema (Dict): The isolated schema dictionary parsed from YAML.

        Returns:
            Dict: A structured dictionary compliant with MongoDB validation rules.
        """

        def convert_type(yaml_type: str) -> str:
            """
            Internal helper mapping human-readable YAML data types to their 
            strict MongoDB BSON type equivalents.
            """
            type_mapping = {
                "str": "string",
                "int": "int",
                "float": "double",
                "bool": "bool",
                "datetime": "date",
                "Dict": "object",
                "List": "array",
                # PATCH: Explicit mapping for List[Dict] to satisfy complex nested array requirements
                "List[Dict]": "array",  
                "List[str]": "array",
            }
            # Return the corresponding BSON type, or fallback to the raw string if unregistered
            return type_mapping.get(yaml_type, yaml_type)

        def process_field(field_def):
            """
            Recursively processes a nested field definition to ensure deep 
            structural compliance with BSON types.
            """
            # Case 1: Terminal string definition (e.g., "str") -> Construct a basic BSON type constraint
            if isinstance(field_def, str):
                return {"bsonType": convert_type(field_def)}

            # Case 2: Nested dictionary (Object) -> Recursively traverse and map internal properties
            elif isinstance(field_def, dict):
                return {
                    "bsonType": "object",
                    "properties": {k: process_field(v) for k, v in field_def.items()},
                }

            # Case 3: Raw list definition -> Enforce standard array constraint
            elif isinstance(field_def, list):
                return {"bsonType": "array"}
            
            return field_def

        # --------------------------------------------------------------------------
        # SCHEMA PROPERTY ASSEMBLY
        # --------------------------------------------------------------------------
        
        properties = {}

        # Process standard attributes shared universally across Digital Replicas (e.g., metadata)
        if "common_fields" in yaml_schema:
            for field_name, field_def in yaml_schema["common_fields"].items():
                properties[field_name] = process_field(field_def)

        # Process domain-specific state parameters defined within the 'entity' block
        if "entity" in yaml_schema and "data" in yaml_schema["entity"]:
            properties["data"] = process_field(yaml_schema["entity"]["data"])

        # --------------------------------------------------------------------------
        # VALIDATION RULES & MANDATORY FIELD INJECTION
        # --------------------------------------------------------------------------
        required_root = []
        validations = yaml_schema.get("validations", {})
        mandatory = validations.get("mandatory_fields", {})

        # Accumulate required fields mapped specifically to the root level of the document
        if "root" in mandatory:
            required_root.extend(mandatory["root"])
            
        # Apply field existence constraints to nested sub-documents ('profile' and 'metadata')
        for sub_section in ["profile", "metadata"]:
            if sub_section in mandatory and sub_section in properties:
                # Inject the 'required' array directly into the specific sub-object's schema node
                properties[sub_section]["required"] = mandatory[sub_section]

        # ┌────────────────────────────────────────────────────────────────┐
        # │ STRICT ARCHITECTURAL COMPLIANCE                                │
        # ├────────────────────────────────────────────────────────────────┤
        # │ Mandate the presence of '_id' and 'type' at the root level,    │
        # │ ensuring consistent indexing and retrieval mechanisms.         │
        # └────────────────────────────────────────────────────────────────┘
        for default_field in ["_id", "type"]:
            if default_field not in required_root:
                required_root.append(default_field)

        # Compile the final schema structure according to MongoDB's explicit $jsonSchema specification
        validation_schema = {
            "$jsonSchema": {
                "bsonType": "object",
                "required": required_root,
                "properties": {
                    "_id": {"bsonType": "string"},
                    "type": {"bsonType": "string"},
                    **properties,  # Dynamically unpack the processed common and entity properties
                },
            }
        }

        return validation_schema

    # --------------------------------------------------------------------------
    # RUNTIME UTILITY ACCESSORS
    # --------------------------------------------------------------------------
    
    def get_collection_name(self, schema_type: str) -> str:
        """
        Derives the designated MongoDB collection name based on the schema classification.

        Args:
            schema_type (str): The targeted Digital Replica type.

        Returns:
            str: The dynamically formatted collection string (e.g., 'pet_collection').
        """
        return f"{schema_type}_collection"

    def get_validation_schema(self, schema_type: str) -> Dict:
        """
        Retrieves the pre-compiled MongoDB validation schema from the memory cache.

        Args:
            schema_type (str): The requested Digital Replica type.

        Returns:
            Dict: The compiled `$jsonSchema` dictionary.

        Raises:
            ValueError: If the requested schema type has not been loaded and compiled.
        """
        if schema_type not in self.schemas:
            raise ValueError(f"Schema compilation missing for designated type: {schema_type}")
        return self.schemas[schema_type]