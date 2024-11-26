from typing import Dict, Any
import yaml

class SchemaRegistry:
    """
    A simplified schema registry that loads and maintains validation schemas.
    The registry accepts any YAML schema and converts it to MongoDB validation rules.
    """
    def __init__(self):
        self.schemas = {}

    def load_schema(self, schema_type: str, yaml_path: str) -> None:
        """
        Load a schema from a YAML file and store it in the registry
        
        Args:
            schema_type: Type identifier for the schema
            yaml_path: Path to the YAML schema file
        """
        try:
            with open(yaml_path, 'r') as file:
                raw_schema = yaml.safe_load(file)
                
            # Convert the raw schema to MongoDB validation format
            validation_schema = self._create_validation_schema(raw_schema)
            self.schemas[schema_type] = validation_schema
                
        except Exception as e:
            raise ValueError(f"Failed to load schema from {yaml_path}: {str(e)}")

    def _create_validation_schema(self, raw_schema: Dict) -> Dict:
        """
        Convert a raw schema into MongoDB validation format
        
        Args:
            raw_schema: The raw schema loaded from YAML
            
        Returns:
            Dict: MongoDB validation schema
        """
        # Basic validation schema with required fields
        validation_schema = {
            '$jsonSchema': {
                'bsonType': 'object',
                'required': ['_id', 'type', 'metadata'],
                'properties': {
                    '_id': {'bsonType': 'string'},
                    'type': {'bsonType': 'string'},
                    'metadata': {
                        'bsonType': 'object',
                        'required': ['created_at', 'updated_at'],
                        'properties': {
                            'created_at': {'bsonType': 'date'},
                            'updated_at': {'bsonType': 'date'}
                        },
                        'additionalProperties': True
                    }
                },
                'additionalProperties': True
            }
        }

        # If schema defines additional validations, merge them
        if raw_schema.get('validations'):
            self._merge_validations(
                validation_schema['$jsonSchema'], 
                raw_schema['validations']
            )

        return validation_schema

    def _merge_validations(self, base_schema: Dict, custom_validations: Dict) -> None:
        """
        Merge custom validations into the base schema
        
        Args:
            base_schema: The base validation schema
            custom_validations: Custom validation rules to merge
        """
        # Add required fields
        if 'required' in custom_validations:
            base_schema['required'].extend(
                field for field in custom_validations['required'] 
                if field not in base_schema['required']
            )

        # Add properties
        if 'properties' in custom_validations:
            if 'properties' not in base_schema:
                base_schema['properties'] = {}
            base_schema['properties'].update(custom_validations['properties'])

    def get_collection_name(self, schema_type: str) -> str:
        """
        Get the collection name for a schema type
        
        Args:
            schema_type: Type of the schema
            
        Returns:
            str: Collection name
        """
        return f"{schema_type}_collection"

    def get_validation_schema(self, schema_type: str) -> Dict:
        """
        Get the validation schema for a type
        
        Args:
            schema_type: Type of the schema
            
        Returns:
            Dict: Validation schema
            
        Raises:
            ValueError: If schema type not found
        """
        if schema_type not in self.schemas:
            raise ValueError(f"Schema not found for type: {schema_type}")
        return self.schemas[schema_type]