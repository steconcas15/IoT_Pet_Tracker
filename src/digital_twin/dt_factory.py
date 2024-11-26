import yaml
from datetime import datetime
from typing import Dict, Any
import uuid


class DRFactory:
    def __init__(self, schema_path: str):
        self.schema = self._load_schema(schema_path)
        if not self.schema or "schemas" not in self.schema:
            raise ValueError(f"Invalid schema structure in {schema_path}")

    def _load_schema(self, path: str) -> Dict:
        try:
            with open(path, "r") as file:
                return yaml.safe_load(file)
        except Exception as e:
            raise ValueError(f"Failed to load schema: {str(e)}")

    def create_dr(self, dr_type: str, initial_data: Dict[str, Any]) -> Dict:
        """Create a Digital Replica based on schema definition"""
        if not self.schema:
            raise ValueError("No schema loaded")

        # Initialize base structure with required fields
        dr = {
            "_id": str(uuid.uuid4()),
            "type": dr_type,  # IMPORTANTE: Questo è il tipo!
            "metadata": {
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "privacy_level": initial_data.get("metadata", {}).get(
                    "privacy_level", "private"
                ),
            },
        }

        # Processa i campi dal profilo
        if "profile" in initial_data:
            dr["profile"] = initial_data["profile"].copy()

        # Processa i campi dai dati
        if "data" in initial_data:
            dr["data"] = initial_data["data"].copy()
        else:
            dr["data"] = {}

        # Assicurati che ci siano i campi obbligatori nei dati
        if "status" not in dr["data"]:
            dr["data"]["status"] = "active"
        if "measurements" not in dr["data"]:
            dr["data"]["measurements"] = []
        if "properties" not in dr["data"]:
            dr["data"]["properties"] = {}
        if "relations" not in dr["data"]:
            dr["data"]["relations"] = {}

        print(f"\n=== Debug: Created DR ===")
        print(f"Type: {dr['type']}")  # Verifica che il tipo sia settato
        print(f"ID: {dr['_id']}")
        print(f"Data: {dr['data']}")

        return dr

    def _process_section(
        self, dr: Dict, initial_data: Dict, section_schema: Dict
    ) -> None:
        """Process a schema section and apply it to the DR"""
        for field, field_def in section_schema.items():
            # Handle nested fields (like profile, data, metadata)
            if isinstance(field_def, dict):
                if field not in dr:
                    dr[field] = {}

                # Get initial data for this field
                source_data = initial_data.get(field, {})

                # Process each subfield
                for subfield, subfield_type in field_def.items():
                    value = source_data.get(subfield)

                    # If value not provided, initialize based on type
                    if value is None:
                        value = self._get_default_value(subfield_type)

                    dr[field][subfield] = value
            else:
                # Handle direct fields
                value = initial_data.get(field)
                if value is None:
                    value = self._get_default_value(field_def)
                dr[field] = value

    def _get_default_value(self, type_def: str) -> Any:
        """Get default value based on type"""
        if isinstance(type_def, list):
            return []
        if type_def == "Dict":
            return {}
        if type_def == "List[Dict]":
            return []
        if type_def == "datetime":
            return datetime.utcnow()
        if type_def == "str":
            return ""
        if type_def == "int":
            return 0
        if type_def == "float":
            return 0.0
        if type_def == "bool":
            return False
        return None

    def _validate_against_schema(self, dr: Dict, validations: Dict) -> None:
        """Validate DR against schema validations"""
        # Check required fields
        if "required" in validations:
            missing = [
                field
                for field in validations["required"]
                if field not in dr or dr[field] is None
            ]
            if missing:
                raise ValueError(f"Missing required fields: {missing}")

        # Check field properties
        if "properties" in validations:
            for field, rules in validations["properties"].items():
                if field not in dr:
                    continue

                value = dr[field]

                # Check required subfields
                if "required" in rules:
                    if not isinstance(value, dict):
                        raise ValueError(f"Field {field} must be an object")
                    missing = [
                        subfield
                        for subfield in rules["required"]
                        if subfield not in value or value[subfield] is None
                    ]
                    if missing:
                        raise ValueError(
                            f"Missing required subfields in {field}: {missing}"
                        )

                # Validate field properties
                if "properties" in rules:
                    for subfield, subrules in rules["properties"].items():
                        if subfield not in value:
                            continue

                        subvalue = value[subfield]

                        # Type validation
                        if "type" in subrules:
                            self._validate_type(
                                subvalue, subrules["type"], f"{field}.{subfield}"
                            )

                        # Range validation
                        if "minimum" in subrules and subvalue < subrules["minimum"]:
                            raise ValueError(
                                f"{field}.{subfield} must be >= {subrules['minimum']}"
                            )
                        if "maximum" in subrules and subvalue > subrules["maximum"]:
                            raise ValueError(
                                f"{field}.{subfield} must be <= {subrules['maximum']}"
                            )

                        # Enum validation
                        if "enum" in subrules and subvalue not in subrules["enum"]:
                            raise ValueError(
                                f"{field}.{subfield} must be one of {subrules['enum']}"
                            )

    def _validate_type(self, value: Any, expected_type: str, field_path: str) -> None:
        """Validate value against expected type"""
        type_mapping = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
        }

        if expected_type in type_mapping:
            expected_class = type_mapping[expected_type]
            if not isinstance(value, expected_class):
                raise ValueError(f"{field_path} must be of type {expected_type}")
