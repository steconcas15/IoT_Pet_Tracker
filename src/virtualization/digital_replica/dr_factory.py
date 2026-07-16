from datetime import datetime, timezone
from typing import Dict, Any, Type, Optional, List, Union
from pydantic import BaseModel, create_model, Field, field_validator
import yaml
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

    def _create_profile_model(self) -> Type[BaseModel]:
        """Create Pydantic model for profile section"""
        mandatory_fields = (
            self.schema["schemas"]
            .get("validations", {})
            .get("mandatory_fields", {})
            .get("profile", [])
        )
        type_constraints = (
            self.schema["schemas"].get("validations", {}).get("type_constraints", {})
        )

        field_definitions = {}
        profile_fields = self.schema["schemas"]["common_fields"].get("profile", {})

        for field_name, field_type in profile_fields.items():
            is_required = field_name in mandatory_fields
            constraints = {}

            if field_name in type_constraints:
                rules = type_constraints[field_name]
                if "min" in rules:
                    constraints["ge"] = rules["min"]
                if "max" in rules:
                    constraints["le"] = rules["max"]

            field_definitions[field_name] = (
                (
                    str
                    if field_type == "str"
                    else (
                        int
                        if field_type == "int"
                        else (
                            float
                            if field_type == "float"
                            else datetime if field_type == "datetime" else Any
                        )
                    )
                ),
                Field(None if not is_required else ..., **constraints),
            )

        validators_dict = {}

        # Add enum validators where needed
        for field_name in field_definitions:
            if (
                field_name in type_constraints
                and "enum" in type_constraints[field_name]
            ):
                enum_values = type_constraints[field_name]["enum"]

                def make_enum_validator(allowed=enum_values, name=field_name):
                    def validate_enum(cls, value):
                        if value not in allowed:
                            raise ValueError(f"{name} must be one of {allowed}")
                        return value
                    return validate_enum

                validators_dict[f"validate_{field_name}"] = field_validator(field_name, mode="before")(
                    make_enum_validator()
                )

        model = create_model("Profile", __validators__=validators_dict, **field_definitions)
        return model

    def _create_data_model(self) -> Type[BaseModel]:
        """Create Pydantic model for data section"""
        type_constraints = (
            self.schema["schemas"].get("validations", {}).get("type_constraints", {})
        )
        data_fields = self.schema["schemas"].get("entity", {}).get("data", {})

        field_definitions = {}
        for field_name, field_type in data_fields.items():
            if field_type == "List[Dict]":
                field_definitions[field_name] = (
                    List[Dict[str, Any]],
                    Field(default_factory=list),
                )
            elif field_type == "List[str]":
                field_definitions[field_name] = (List[str], Field(default_factory=list))
            else:
                field_definitions[field_name] = (
                    (
                        str
                        if field_type == "str"
                        else (
                            int
                            if field_type == "int"
                            else float if field_type == "float" else Any
                        )
                    ),
                    Field(None),
                )

        validators_dict = {}

        # Add validators for fields that need them
        for field_name, field_type in data_fields.items():
            if (
                field_name in type_constraints
                and "enum" in type_constraints[field_name]
            ):
                enum_values = type_constraints[field_name]["enum"]

                def make_enum_validator(allowed=enum_values, name=field_name):
                    def validate_enum(cls, value):
                        if value not in allowed:
                            raise ValueError(f"{name} must be one of {allowed}")
                        return value
                    return validate_enum

                validators_dict[f"validate_{field_name}"] = field_validator(field_name, mode="before")(
                    make_enum_validator()
                )

            if field_type == "List[Dict]" and field_name in type_constraints:
                rules = type_constraints[field_name]
                if "item_constraints" in rules:
                    item_rules = rules["item_constraints"]
                    required_fields = item_rules.get("required_fields", [])
                    type_mappings = item_rules.get("type_mappings", {})

                    def make_list_validator(req_f=required_fields, t_map=type_mappings, f_n=field_name):
                        def validate_list_items(cls, value):
                            if not isinstance(value, list):
                                raise ValueError(f"{f_n} must be a list")

                            for idx, item in enumerate(value):
                                if not isinstance(item, dict):
                                    raise ValueError(
                                        f"Item {idx} in {f_n} must be a dictionary"
                                    )

                                missing = [f for f in req_f if f not in item]
                                if missing:
                                    raise ValueError(
                                        f"Missing required fields {missing} in item {idx}"
                                )

                                for key, expected_type in t_map.items():
                                    if key in item:
                                        val = item[key]
                                        if expected_type == "datetime":
                                            if not isinstance(val, (datetime, str)):
                                                raise ValueError(
                                                    f"Field {key} in item {idx} must be a datetime"
                                                )
                                        elif expected_type == "float":
                                            try:
                                                item[key] = float(val)
                                            except (TypeError, ValueError):
                                                raise ValueError(
                                                    f"Field {key} in item {idx} must be a number"
                                                )
                            return value
                        return validate_list_items

                    validators_dict[f"validate_{field_name}"] = field_validator(field_name, mode="before")(
                        make_list_validator()
                    )

        model = create_model("Data", __validators__=validators_dict, **field_definitions)
        return model

    def create_dr(self, dr_type: str, initial_data: Dict[str, Any]) -> Dict:
        """Create a new Digital Replica instance"""
        ProfileModel = self._create_profile_model()
        DataModel = self._create_data_model()

        dr_dict = {
            "_id": str(uuid.uuid4()),
            "type": dr_type,
            "metadata": {
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            },
            "data": {},
        }

        init_values = (
            self.schema["schemas"].get("validations", {}).get("initialization", {})
        )
        for section, defaults in init_values.items():
            if section == "metadata":
                dr_dict["metadata"].update(defaults)
            elif section in [
                "status",
                "sensors",
                "devices",
                "esp32cam_device",
                "ultrasonic_sensors",
                "occupancy_stats",
                "buzzer",
                "current_room",
                "buzzer_status",
                "daily_buzzer_stats"
            ]:
                dr_dict["data"][section] = defaults
            else:
                dr_dict[section] = defaults

        if "profile" in initial_data:
            profile = ProfileModel(**initial_data["profile"])
            dr_dict["profile"] = profile.model_dump(exclude_unset=True)

        if "data" in initial_data:
            data = DataModel(**{**dr_dict["data"], **initial_data["data"]})
            dr_dict["data"] = data.model_dump(exclude_unset=True)

        if "metadata" in initial_data:
            dr_dict["metadata"].update(initial_data["metadata"])

        return dr_dict

    def update_dr(self, dr: Dict[str, Any], updates: Dict[str, Any]) -> Dict:
        """Update an existing Digital Replica"""
        ProfileModel = self._create_profile_model()
        DataModel = self._create_data_model()

        updated_dr = dr.copy()

        if "profile" in updates:
            current_profile = updated_dr.get("profile", {})
            profile = ProfileModel(**(current_profile | updates["profile"]))
            updated_dr["profile"] = profile.model_dump(exclude_unset=True)

        if "data" in updates:
            current_data = updated_dr.get("data", {})
            data = DataModel(**(current_data | updates["data"]))
            updated_dr["data"] = data.model_dump(exclude_unset=True)

        if "metadata" in updates:
            updated_dr["metadata"].update(updates["metadata"])

        updated_dr["metadata"]["updated_at"] = datetime.now(timezone.utc)

        return updated_dr