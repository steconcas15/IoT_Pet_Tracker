import yaml
from datetime import datetime
from typing import Dict, Any
import copy
import uuid


class DRFactory:
    def __init__(self, schema_path: str):
        self.schema = self._load_schema(schema_path)
        if not self.schema:
            raise ValueError(f"Failed to load schema from {schema_path}")

    def _load_schema(self, path: str) -> Dict:
        try:
            with open(path, "r") as file:
                schema = yaml.safe_load(file)
                if not schema or "schemas" not in schema:
                    raise ValueError(
                        "Invalid schema structure - You need to load a yaml schema for this kind of DR"
                    )
                return schema
        except Exception as e:
            raise ValueError(f"Failed to load schema: {str(e)}")

    def create_dr(self, dr_type: str, initial_data: Dict[str, Any]) -> Dict:
        """
        Crea un nuovo Digital Replica basato sullo schema e i dati iniziali.
        Verifica che i dati rispettino la struttura dello schema.
        """
        if not self.schema or "schemas" not in self.schema:
            raise ValueError("No valid schema loaded")

        # Validazione contro lo schema
        self._validate_data(initial_data)

        dr_base = {
            "_id": initial_data.get("id", str(uuid.uuid4())),
            "type": dr_type,
            "profile": {
                "name": initial_data.get("profile", {}).get("name"),
                "description": initial_data.get("profile", {}).get("description"),
            },
            "metadata": {
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "privacy_level": initial_data.get("privacy_level", "private"),
            },
            "data": {
                "status": initial_data.get("status", "active"),
                "properties": initial_data.get("properties", {}),
                "measurements": initial_data.get("measurements", []),
                "relations": initial_data.get("relations", {}),
            },
        }

        return dr_base

    def _validate_data(self, data: Dict) -> None:
        """
        Verifica che i dati rispettino la struttura definita nello schema
        """
        if not self.schema or "schemas" not in self.schema:
            raise ValueError("Cannot validate: no valid schema loaded")

        required_fields = {"profile": {"name", "description"}, "data": {"status"}}

        # Verifica profilo
        if "profile" not in data:
            raise ValueError("Missing profile data")

        profile = data.get("profile", {})
        missing_profile = required_fields["profile"] - set(profile.keys())
        if missing_profile:
            raise ValueError(f"Missing required profile fields: {missing_profile}")

        # Verifica misurazioni se presenti
        if "measurements" in data:
            for m in data["measurements"]:
                if not all(k in m for k in ("measure_type", "value", "timestamp")):
                    raise ValueError(
                        "Invalid measurement format. Required: measure_type, value, timestamp"
                    )

        # Verifica dati
        if "data" in data:
            data_fields = required_fields["data"] - set(data["data"].keys())
            if data_fields:
                raise ValueError(f"Missing required data fields: {data_fields}")
