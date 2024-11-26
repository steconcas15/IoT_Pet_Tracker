from typing import Dict, List, Optional
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import PyMongoError
from datetime import datetime
from src.virtualization.digital_replica.schema_registry import SchemaRegistry

class DatabaseService:
    def __init__(self, connection_string: str, db_name: str, schema_registry: SchemaRegistry):
        self.connection_string = connection_string
        self.db_name = db_name
        self.schema_registry = schema_registry
        self.client: Optional[MongoClient] = None
        self.db: Optional[Database] = None
        self._connected = False

    def connect(self) -> None:
        try:
            self.client = MongoClient(self.connection_string)
            self.db = self.client[self.db_name]
            # Test connection
            self.client.server_info()
            self._connected = True
        except Exception as e:
            self._connected = False
            raise ConnectionError(f"Failed to connect to MongoDB: {str(e)}")

    def disconnect(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None
            self.db = None
            self._connected = False

    def is_connected(self) -> bool:
        return self._connected and self.client is not None and self.db is not None

    def init_collections(self) -> None:
        """Initialize collections in MongoDB based on registered schemas"""
        if not self.is_connected():
            raise ConnectionError("Not connected to MongoDB")

        try:
            existing_collections = self.db.list_collection_names()

            # Drop existing collections
            for collection in existing_collections:
                self.db.drop_collection(collection)

            # Create collections for all registered schemas
            for dr_type in self.schema_registry.schemas.keys():
                collection_name = self.schema_registry.get_collection_name(dr_type)
                validation_schema = self.schema_registry.get_validation_schema(dr_type)

                # Create collection with schema validation
                self.db.create_collection(
                    collection_name,
                    validator=validation_schema,
                    validationAction="error"
                )

                # Create standard indexes for all collections
                collection = self.db[collection_name]
                collection.create_index("type")
                collection.create_index([("metadata.created_at", 1)])
                collection.create_index([("metadata.updated_at", 1)])

                # Create index on the id field which is always required
                collection.create_index("_id", unique=True)

        except Exception as e:
            raise Exception(f"Failed to initialize collections: {str(e)}")

    def save_dr(self, dr_type: str, data: Dict) -> str:
        if not self.is_connected():
            raise ConnectionError("Not connected to MongoDB")

        try:
            collection = self.db[self.schema_registry.get_collection_name(dr_type)]
            result = collection.insert_one(data)
            return str(result.inserted_id)
        except Exception as e:
            raise Exception(f"Failed to save DR: {str(e)}")

    def get_dr(self, dr_type: str, dr_id: str) -> Optional[Dict]:
        if not self.is_connected():
            raise ConnectionError("Not connected to MongoDB")

        try:
            collection = self.db[self.schema_registry.get_collection_name(dr_type)]
            return collection.find_one({"_id": dr_id})
        except Exception as e:
            raise Exception(f"Failed to retrieve DR: {str(e)}")

    def update_dr(self, dr_type: str, dr_id: str, update_data: Dict) -> None:
        if not self.is_connected():
            raise ConnectionError("Not connected to MongoDB")

        try:
            collection = self.db[self.schema_registry.get_collection_name(dr_type)]
            if "metadata" not in update_data:
                update_data["metadata"] = {}
            update_data["metadata"]["updated_at"] = datetime.utcnow()

            result = collection.update_one(
                {"_id": dr_id},
                {"$set": update_data}
            )

            if result.matched_count == 0:
                raise ValueError(f"DR not found with id: {dr_id}")
        except Exception as e:
            raise Exception(f"Failed to update DR: {str(e)}")

    def query_drs(self, dr_type: str, query: Dict) -> List[Dict]:
        if not self.is_connected():
            raise ConnectionError("Not connected to MongoDB")

        try:
            collection = self.db[self.schema_registry.get_collection_name(dr_type)]
            return list(collection.find(query))
        except Exception as e:
            raise Exception(f"Failed to query DRs: {str(e)}")

    def delete_dr(self, dr_type: str, dr_id: str) -> None:
        """Elimina un Digital Replica"""
        if not self.is_connected():
            raise ConnectionError("Not connected to MongoDB")

        try:
            collection = self.db[self.schema_registry.get_collection_name(dr_type)]
            result = collection.delete_one({"_id": dr_id})
            if result.deleted_count == 0:
                raise ValueError(f"DR not found with id: {dr_id}")
        except Exception as e:
            raise Exception(f"Failed to delete DR: {str(e)}")

    def delete_all(self, dr_type: str) -> None:
        """Elimina tutti i Digital Replica di un tipo specifico"""
        if not self.is_connected():
            raise ConnectionError("Not connected to MongoDB")

        try:
            collection = self.db[self.schema_registry.get_collection_name(dr_type)]
            collection.delete_many({})
        except Exception as e:
            raise Exception(f"Failed to delete DRs: {str(e)}")
