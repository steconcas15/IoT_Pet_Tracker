import yaml
from datetime import datetime
from typing import Dict, Any
import copy
import uuid


class DRFactory:
    def __init__(self, schema_path: str):
        self.schema = self._load_schema(schema_path)

    def _load_schema(self, path: str) -> Dict:
        with open(path, "r") as file:
            return yaml.safe_load(file)

    def create_dr(self, dr_type: str, initial_data: Dict[str, Any]) -> Dict:
        if dr_type not in self.schema:
            raise ValueError(f"No schema loaded for type: {dr_type}")
        dr_base = {
            "id": initial_data.get("id", str(uuid.uuid4())),
            "type": dr_type,
            "profile": copy.deepcopy(
                self.schema["schemas"]["common_fields"]["profile"]
            ),
            "metadata": {
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "privacy_level": initial_data.get("privacy_level", "private"),
            },
            "data": {
                "status": initial_data.get("status", "active"),
                "properties": {},  # Nuovo campo per proprietà specifiche
                "measurements": [],
                "relations": {},  # Nuovo campo per relazioni
            },
        }

        # Aggiornamento properties specifiche del tipo
        if "properties" in initial_data:
            dr_base["data"]["properties"] = initial_data["properties"]

        # Aggiornamento relazioni
        if "relations" in initial_data:
            dr_base["data"]["relations"] = initial_data["relations"]

        return dr_base
