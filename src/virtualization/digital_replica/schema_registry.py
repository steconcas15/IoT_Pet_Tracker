from typing import Dict, Any
import yaml

# ==============================================================================
# SCHEMA REGISTRY COMPONENT
# ==============================================================================
# This class acts as the central translator and storage for data schemas.
# It reads validation rules from YAML files and converts them into MongoDB's
# native $jsonSchema format.
# ==============================================================================

class SchemaRegistry:
    def __init__(self):
        """
        [CONSTRUCTOR]
        Initializes an empty dictionary to hold all processed schemas,
        indexed by their type.
        """
        self.schemas = {}

    # --------------------------------------------------------------------------
    # YAML LOADING & PROCESSING
    # --------------------------------------------------------------------------
    
    def load_schema(self, schema_type: str, yaml_path: str) -> None:
        """Load schema from YAML file"""
        try:
            # Opens the specified YAML file in read-only mode ("r")
            with open(yaml_path, "r") as file:
                # Safely parses the raw YAML content into a standard Python dictionary
                raw_schema = yaml.safe_load(file)

            # Sanity check: ensures the file isn't empty and contains the root "schemas" key
            if not raw_schema or "schemas" not in raw_schema:
                raise ValueError(f"Invalid schema structure in {yaml_path}")

            # ┌────────────────────────────────────────────────────────────────┐
            # │                     CONVERSION PIPELINE                        │
            # ├────────────────────────────────────────────────────────────────┤
            # │ Extracts the "schemas" block from the YAML and passes it to    │
            # │ the internal conversion engine to map out the MongoDB format.  │
            # └────────────────────────────────────────────────────────────────┘
            validation_schema = self._convert_yaml_to_mongodb_schema(
                raw_schema["schemas"]
            )

            # Cache the fully compiled MongoDB schema using the type as the key
            self.schemas[schema_type] = validation_schema

        except Exception as e:
            # Catch-all for missing files, syntax issues, or corrupted YAMLs
            raise ValueError(f"Failed to load schema from {yaml_path}: {str(e)}")

    # --------------------------------------------------------------------------
    # CONVERSION ENGINE (YAML -> MONGOdb)
    # --------------------------------------------------------------------------
    def _convert_yaml_to_mongodb_schema(self, yaml_schema: Dict) -> Dict:
        """Convert YAML schema format to MongoDB $jsonSchema format"""

        def convert_type(yaml_type: str) -> str:
            """Convert YAML type to MongoDB BSON type"""

            # Maps human-readable YAML data types to their strict MongoDB BSON equivalents
            
            type_mapping = {
                "str": "string",
                "int": "int",
                "float": "double",
                "bool": "bool",
                "datetime": "date",
                "Dict": "object",
                "List": "array",
                "List[Dict]": "array",  # <-- CORREZIONE: Supporto per List[Dict] richiesto dal README
                "List[str]": "array",
            }
            # Returns the matched BSON type, or falls back to the original string if not found
            return type_mapping.get(yaml_type, yaml_type)

        def process_field(field_def):
            """Process a field definition from YAML to MongoDB format"""

            # Case 1: Simple string type definition (e.g., "str") -> Build a basic BSON type rule
            if isinstance(field_def, str):
                return {"bsonType": convert_type(field_def)}

            # Case 2: Nested dictionary (sub-object) -> Recursively process its internal properties
            elif isinstance(field_def, dict):
                return {
                    "bsonType": "object",
                    "properties": {k: process_field(v) for k, v in field_def.items()},
                }

            # Case 3: Raw list definition -> Explicitly set it as an array type constraint
            elif isinstance(field_def, list):
                return {"bsonType": "array"}
            return field_def

        # --------------------------------------------------------------------------
        # BUILDING SCHEMA PROPERTIES
        # --------------------------------------------------------------------------
        
        properties = {}

        # If the YAML defines common_fields shared by everyone (e.g., shared metadata), process them here
        if "common_fields" in yaml_schema:
            for field_name, field_def in yaml_schema["common_fields"].items():
                properties[field_name] = process_field(field_def)

        # If specific digital twin entity payload fields exist inside "data", nest them under the "data" object
        if "entity" in yaml_schema and "data" in yaml_schema["entity"]:
            properties["data"] = process_field(yaml_schema["entity"]["data"])

        # --------------------------------------------------------------------------
        # VALIDATIONS & MANDATORY FIELDS INJECTION
        # --------------------------------------------------------------------------
        required_root = []
        validations = yaml_schema.get("validations", {})
        mandatory = validations.get("mandatory_fields", {})

        # Extract the list of required fields that must live at the root level
        if "root" in mandatory:
            required_root.extend(mandatory["root"])
            
       # Apply field constraints to sub-sections ('profile' and 'metadata') if they are defined
        for sub_section in ["profile", "metadata"]:
            if sub_section in mandatory and sub_section in properties:
                # Inject the array of required fields directly inside that specific object's definition
                properties[sub_section]["required"] = mandatory[sub_section]

        # ┌────────────────────────────────────────────────────────────────┐
        # │ STRICT STRUCTURAL COMPLIANCE                                   │
        # ├────────────────────────────────────────────────────────────────┤
        # │ Enforce '_id' and 'type' at the root level, ensuring every     │
        # │ registered Digital Twin document can be properly identified.   │
        # └────────────────────────────────────────────────────────────────┘
        for default_field in ["_id", "type"]:
            if default_field not in required_root:
                required_root.append(default_field)

        # Assemble the final schema structure according to MongoDB's $jsonSchema spec
        validation_schema = {
            "$jsonSchema": {
                "bsonType": "object",
                "required": required_root,
                "properties": {
                    "_id": {"bsonType": "string"},
                    "type": {"bsonType": "string"},
                    **properties,        # Merges the processed common and entity fields dynamically
                },
            }
        }

        return validation_schema

    # --------------------------------------------------------------------------
    # UTILITY METHODS
    # --------------------------------------------------------------------------
    
    def get_collection_name(self, schema_type: str) -> str:
        """Get collection name for schema type"""
        # Dynamically formats the corresponding target MongoDB collection name (e.g., "pet_collection")
        return f"{schema_type}_collection"

    def get_validation_schema(self, schema_type: str) -> Dict:
        """Get validation schema for type"""
        # Fetches the compiled schema from the registry cache. Blows up with an error if it doesn't exist.
        if schema_type not in self.schemas:
            raise ValueError(f"Schema not found for type: {schema_type}")
        return self.schemas[schema_type]
