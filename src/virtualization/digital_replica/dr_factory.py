"""
Digital Replica Factory & Validation Module
===========================================
This module implements the Factory Design Pattern combined with dynamic metaprogramming 
to instantiate, validate, and mutate Digital Replicas (DRs). 

It leverages the `pydantic` library to dynamically construct data validation models 
at runtime based on constraints defined in external YAML schema files. This ensures 
strict structural integrity and type safety for all entities (e.g., rooms, doors, pets) 
within the Digital Twin architecture.
"""

from datetime import datetime, timezone
from typing import Dict, Any, Type, Optional, List, Union
from pydantic import BaseModel, create_model, Field, field_validator
import yaml
import uuid


class DRFactory:
    """
    Factory class responsible for dynamically generating robust Digital Replica instances.
    It parses YAML-defined schemas to construct runtime Pydantic validation models,
    ensuring that all incoming data adheres strictly to system constraints before persistence.
    """

    def __init__(self, schema_path: str):
        """
        Initializes the factory by loading and parsing the specified YAML schema.

        Args:
            schema_path (str): The file path to the YAML schema definition.

        Raises:
            ValueError: If the schema file is unreadable or lacks the required root 'schemas' node.
        """
        self.schema = self._load_schema(schema_path)
        if not self.schema or "schemas" not in self.schema:
            raise ValueError(f"Invalid schema structure detected in {schema_path}")

    def _load_schema(self, path: str) -> Dict:
        """
        Safely loads and parses a YAML configuration file from the filesystem.

        Args:
            path (str): The absolute or relative path to the YAML file.

        Returns:
            Dict: A dictionary representation of the parsed YAML structure.

        Raises:
            ValueError: If file parsing fails due to syntax errors or missing files.
        """
        try:
            with open(path, "r") as file:
                return yaml.safe_load(file)
        except Exception as e:
            raise ValueError(f"Failed to load schema: {str(e)}")

    def _create_profile_model(self) -> Type[BaseModel]:
        """
        Dynamically constructs a Pydantic validation model for the 'profile' section 
        of a Digital Replica based on the loaded YAML schema.

        Returns:
            Type[BaseModel]: A dynamically generated Pydantic BaseModel subclass.
        """
        # Extract mandatory fields and type-specific boundary constraints
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

        # Iterate through the schema to map YAML types to Python native types and Pydantic constraints
        for field_name, field_type in profile_fields.items():
            is_required = field_name in mandatory_fields
            constraints = {}

            # Apply numerical boundary constraints (greater/less than or equal)
            if field_name in type_constraints:
                rules = type_constraints[field_name]
                if "min" in rules:
                    constraints["ge"] = rules["min"]
                if "max" in rules:
                    constraints["le"] = rules["max"]

            # Map string descriptors to native Python type classes
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

        # Dynamically attach enumeration validators using closures to capture loop variables safely
        for field_name in field_definitions:
            if (
                field_name in type_constraints
                and "enum" in type_constraints[field_name]
            ):
                enum_values = type_constraints[field_name]["enum"]

                def make_enum_validator(allowed=enum_values, name=field_name):
                    def validate_enum(cls, value):
                        if value not in allowed:
                            raise ValueError(f"{name} must be strictly one of {allowed}")
                        return value
                    return validate_enum

                # Register the field validator to execute before standard parsing
                validators_dict[f"validate_{field_name}"] = field_validator(field_name, mode="before")(
                    make_enum_validator()
                )

        # Utilize Pydantic's metaprogramming capabilities to instantiate the class at runtime
        model = create_model("Profile", __validators__=validators_dict, **field_definitions)
        return model

    def _create_data_model(self) -> Type[BaseModel]:
        """
        Dynamically constructs a Pydantic validation model for the 'data' (state) section 
        of a Digital Replica, handling complex nested lists and custom constraints.

        Returns:
            Type[BaseModel]: A dynamically generated Pydantic BaseModel subclass.
        """
        type_constraints = (
            self.schema["schemas"].get("validations", {}).get("type_constraints", {})
        )
        data_fields = self.schema["schemas"].get("entity", {}).get("data", {})

        field_definitions = {}
        # Parse data fields and construct typing definitions, particularly handling collections
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

        # Attach validators for enums and complex nested structures
        for field_name, field_type in data_fields.items():
            # Apply enumeration constraints
            if (
                field_name in type_constraints
                and "enum" in type_constraints[field_name]
            ):
                enum_values = type_constraints[field_name]["enum"]

                def make_enum_validator(allowed=enum_values, name=field_name):
                    def validate_enum(cls, value):
                        if value not in allowed:
                            raise ValueError(f"{name} must be strictly one of {allowed}")
                        return value
                    return validate_enum

                validators_dict[f"validate_{field_name}"] = field_validator(field_name, mode="before")(
                    make_enum_validator()
                )

            # Apply structural constraints for arrays of dictionaries (e.g., historical stats)
            if field_type == "List[Dict]" and field_name in type_constraints:
                rules = type_constraints[field_name]
                if "item_constraints" in rules:
                    item_rules = rules["item_constraints"]
                    required_fields = item_rules.get("required_fields", [])
                    type_mappings = item_rules.get("type_mappings", {})

                    def make_list_validator(req_f=required_fields, t_map=type_mappings, f_n=field_name):
                        def validate_list_items(cls, value):
                            if not isinstance(value, list):
                                raise ValueError(f"{f_n} must be an array/list type")

                            for idx, item in enumerate(value):
                                if not isinstance(item, dict):
                                    raise ValueError(
                                        f"Item at index {idx} in {f_n} must be a dictionary object"
                                    )

                                # Ensure all required keys are present in the dictionary
                                missing = [f for f in req_f if f not in item]
                                if missing:
                                    raise ValueError(
                                        f"Missing required fields {missing} in item at index {idx}"
                                    )

                                # Enforce type safety within nested dictionary values
                                for key, expected_type in t_map.items():
                                    if key in item:
                                        val = item[key]
                                        if expected_type == "datetime":
                                            if not isinstance(val, (datetime, str)):
                                                raise ValueError(
                                                    f"Field '{key}' in item {idx} must be a valid datetime"
                                                )
                                        elif expected_type == "float":
                                            try:
                                                item[key] = float(val)
                                            except (TypeError, ValueError):
                                                raise ValueError(
                                                    f"Field '{key}' in item {idx} must be castable to a numeric float"
                                                )
                            return value
                        return validate_list_items

                    validators_dict[f"validate_{field_name}"] = field_validator(field_name, mode="before")(
                        make_list_validator()
                    )

        model = create_model("Data", __validators__=validators_dict, **field_definitions)
        return model

    def create_dr(self, dr_type: str, initial_data: Dict[str, Any]) -> Dict:
        """
        Provisions a new Digital Replica dictionary, applying schema validation 
        and injecting default metadata before persistence.

        Args:
            dr_type (str): The categorical classification of the replica.
            initial_data (Dict[str, Any]): The raw data payload to instantiate the replica with.

        Returns:
            Dict: A fully validated and initialized dictionary representing the Digital Replica.
        """
        # Instantiate validation classes dynamically
        ProfileModel = self._create_profile_model()
        DataModel = self._create_data_model()

        # Construct the foundational blueprint
        dr_dict = {
            "_id": str(uuid.uuid4()),
            "type": dr_type,
            "metadata": {
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            },
            "data": {},
        }

        # Resolve initialization defaults specified in the schema
        init_values = (
            self.schema["schemas"].get("validations", {}).get("initialization", {})
        )
        for section, defaults in init_values.items():
            if section == "metadata":
                dr_dict["metadata"].update(defaults)
            elif section in [
                "status",
                "occupancy_stats",
                "owned_homes",
                "viewable_homes"
            ]:
                dr_dict["data"][section] = defaults
            else:
                dr_dict[section] = defaults

        # Validate and serialize the 'profile' section
        if "profile" in initial_data:
            profile = ProfileModel(**initial_data["profile"])
            dr_dict["profile"] = profile.model_dump(exclude_unset=True)

        # Validate and serialize the 'data' section, preserving schema defaults
        if "data" in initial_data:
            data = DataModel(**{**dr_dict["data"], **initial_data["data"]})
            dr_dict["data"] = data.model_dump(exclude_unset=True)

        # Append explicit metadata overrides if provided
        if "metadata" in initial_data:
            dr_dict["metadata"].update(initial_data["metadata"])

        return dr_dict

    def update_dr(self, dr: Dict[str, Any], updates: Dict[str, Any]) -> Dict:
        """
        Mutates an existing Digital Replica, enforcing Pydantic schema constraints 
        on the resulting merged state and synchronizing the chronological metadata.

        Args:
            dr (Dict[str, Any]): The current state dictionary of the replica.
            updates (Dict[str, Any]): The delta payload containing state modifications.

        Returns:
            Dict: The re-validated, updated dictionary representing the replica.
        """
        # Re-initialize dynamic models for delta validation
        ProfileModel = self._create_profile_model()
        DataModel = self._create_data_model()

        # Prevent arbitrary mutations on the original dictionary Reference
        updated_dr = dr.copy()

        # Merge and validate the 'profile' modifications
        if "profile" in updates:
            current_profile = updated_dr.get("profile", {})
            profile = ProfileModel(**(current_profile | updates["profile"]))
            updated_dr["profile"] = profile.model_dump(exclude_unset=True)

        # Merge and validate the 'data' (state) modifications
        if "data" in updates:
            current_data = updated_dr.get("data", {})
            data = DataModel(**(current_data | updates["data"]))
            updated_dr["data"] = data.model_dump(exclude_unset=True)

        # Explicit metadata overrides
        if "metadata" in updates:
            updated_dr["metadata"].update(updates["metadata"])

        # Strictly enforce chronological integrity by updating the modification timestamp
        updated_dr["metadata"]["updated_at"] = datetime.now(timezone.utc)

        return updated_dr