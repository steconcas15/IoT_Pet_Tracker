"""
Database Management Service Module
==================================
This module provides a robust abstraction layer over PyMongo, managing all 
CRUD (Create, Read, Update, Delete) operations within the MongoDB cluster. 

It dynamically resolves collection names and structural validation rules by 
interfacing with the centralized `SchemaRegistry`, ensuring data integrity 
for all Digital Replicas and User entities.
"""

from typing import Dict, List, Optional, Any
from pymongo import MongoClient
from datetime import datetime
from src.virtualization.digital_replica.schema_registry import SchemaRegistry
from bson import ObjectId

class DatabaseService:
    """
    Service responsible for managing MongoDB lifecycle connections and handling 
    persistence operations for Digital Replicas (DRs) and Users. It utilizes 
    a SchemaRegistry for dynamic collection resolution.
    """

    # ==============================================================================
    # 1. CONSTRUCTOR & SETUP
    # ==============================================================================
    
    def __init__(
        self, connection_string: str, db_name: str, schema_registry: SchemaRegistry
    ):
        """
        Initializes the database service configuration parameters.
        
        Integration Note:
            This instance is provisioned during the main application bootstrap:
            - connection_string: derived via ConfigLoader (e.g., "mongodb://localhost:27017")
            - db_name: targeting the specific logical database (e.g., "pet_tracker_db")
            - schema_registry: the injected dependency holding replica schemas
        """
        self.connection_string = connection_string
        self.db_name = db_name
        self.schema_registry = schema_registry
        
        # Active PyMongo client instance (instantiated upon connect())
        self.client = None
        # Target MongoDB database reference pointer
        self.db = None

    # ==============================================================================
    # 2. ESTABLISH CONNECTION
    # ==============================================================================
    def connect(self) -> None:
        """
        Initializes the connection pool to the MongoDB cluster using the provided URI.
        
        Raises:
            ConnectionError: If the client fails to authenticate or reach the host.
        """
        try:
            self.client = MongoClient(self.connection_string)
            self.db = self.client[self.db_name]
        except Exception as e:
            raise ConnectionError(f"Failed to establish connection to MongoDB: {str(e)}")

    # ==============================================================================
    # 3. TERMINATE CONNECTION
    # ==============================================================================            
    def disconnect(self) -> None:
        """
        Gracefully terminates the active MongoDB connection and nullifies the state,
        preventing memory leaks or dangling sockets during application shutdown.
        """
        if self.client:
            self.client.close()
            self.client = None
            self.db = None

    # ==============================================================================
    # 4. CONNECTION STATUS CHECK
    # ==============================================================================
    def is_connected(self) -> bool:
        """
        Evaluates whether the client and database references are actively populated.
        
        Returns:
            bool: True if connected, False otherwise.
        """
        return self.client is not None and self.db is not None

    # ==============================================================================
    # 5. CREATE: SAVE DIGITAL REPLICA
    # ==============================================================================
    def save_dr(self, dr_type: str, dr_data: Dict) -> str:
        """
        Persists a newly instantiated Digital Replica into its designated collection.

        The target collection name is dynamically resolved through the SchemaRegistry 
        based on the replica classification (dr_type).
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to MongoDB.")

        try:
            # =====================================================================
            # 1. Navigates to the schema definition (e.g., `replica.yaml`),
            # extracts the identifier from the `type` field, and generates 
            # the target collection name (e.g., `room_collection`).
            # =====================================================================
            collection_name = self.schema_registry.get_collection_name(dr_type)
            
            # =====================================================================
            # 2. Retrieves the structural schema. If the replica type is not 
            # registered within `schemas{}`, an exception is thrown.
            # =====================================================================
            validation_schema = self.schema_registry.get_validation_schema(dr_type)

            # Dynamically attach to the correct MongoDB collection
            collection = self.db[collection_name]

            # Execute the document insertion and return the generated primary key
            result = collection.insert_one(dr_data)
            return str(dr_data["_id"])
        except Exception as e:
            raise Exception(f"Failed to persist Digital Replica: {str(e)}")

    # ==============================================================================
    # 6. READ: GET BY UNIQUE ID
    # ==============================================================================
    def get_dr(self, dr_type: str, dr_id: str) -> Optional[Dict]:
        """
        Retrieves a singular Digital Replica document utilizing its unique primary key (_id).
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to MongoDB.")

        try:
            # Dynamically resolve the corresponding collection string
            collection_name = self.schema_registry.get_collection_name(dr_type)

            # Execute a point-query utilizing the primary key index
            return self.db[collection_name].find_one({"_id": dr_id})
        except Exception as e:
            raise Exception(f"Failed to fetch Digital Replica: {str(e)}")

    # ==============================================================================
    # 7. READ: QUERY MULTIPLE REPLICAS
    # ==============================================================================
    def query_drs(self, dr_type: str, query: Dict = None) -> List[Dict]:
        """
        Executes an arbitrary search query against a specific Digital Replica collection.
        Returns a populated array of matching document dictionaries.
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to MongoDB.")

        try:
            # Resolve collection routing mapping
            collection_name = self.schema_registry.get_collection_name(dr_type)
            # Evaluate the query (fallback to an empty dict for full collection scan)
            return list(self.db[collection_name].find(query or {}))
        except Exception as e:
            raise Exception(f"Failed to query Digital Replicas: {str(e)}")

    # ==============================================================================
    # 8. UPDATE: MODIFY EXISTING DIGITAL REPLICA
    # ==============================================================================
    def update_dr(self, dr_type: str, dr_id: str, update_data: Dict) -> None:
        """
        Performs a partial update on an existing Digital Replica document.
        Automatically intercepts the payload to inject a precise UTC timestamp 
        reflecting the modification event.
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to MongoDB.")

        try:
            collection_name = self.schema_registry.get_collection_name(dr_type)

            # Enforce metadata structure and update the chronological timestamp
            if "metadata" not in update_data:
                update_data["metadata"] = {}
            update_data["metadata"]["updated_at"] = datetime.utcnow()

            # Execute the partial update explicitly using the atomic $set operator
            result = self.db[collection_name].update_one(
                {"_id": dr_id}, {"$set": update_data}
            )

            # Validate that the target identifier actually exists in the database
            if result.matched_count == 0:
                raise ValueError(f"Target Digital Replica not found: {dr_id}")

        except Exception as e:
            raise Exception(f"Failed to update Digital Replica: {str(e)}")

    # ==============================================================================
    # 9. DELETE: REMOVE RECORD
    # ==============================================================================
    def delete_dr(self, dr_type: str, dr_id: str) -> None:
        """
        Permanently eliminates a singular Digital Replica document from the database.
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to MongoDB.")

        try:
            collection_name = self.schema_registry.get_collection_name(dr_type)
            result = self.db[collection_name].delete_one({"_id": dr_id})

            # Confirm physical deletion occurred
            if result.deleted_count == 0:
                raise ValueError(f"Target Digital Replica not found: {dr_id}")
        except Exception as e:
            raise Exception(f"Failed to delete Digital Replica: {str(e)}")


    # ==============================================================================
    # 10. ROLE VERIFICATION (ADMIN / VIEWER)
    # ==============================================================================
    def is_home_admin(self, dt_id: str, user_id: str) -> bool:
        """
        Verifies if a specific Home Environment ID exists within a user's 'owned_homes' array, 
        thereby confirming administrative ownership privileges.
        """
        try:
            collection_name = self.schema_registry.get_collection_name("user")
            
            # Cast to ObjectId for native MongoDB comparison if applicable
            valid_id = ObjectId(user_id) if ObjectId.is_valid(user_id) else user_id
            
            # Query the user document matching the ID and possessing the target home
            user = self.db[collection_name].find_one({
                "_id": valid_id,
                "data.owned_homes": dt_id
            })
            return user is not None
        except Exception as e:
            raise Exception(f"Error during administrative permission validation: {str(e)}")

    # ==============================================================================
    # 12. VIEWABLE HOMES MANAGEMENT
    # ==============================================================================
    def add_viewable_home(self, user_id: str, dt_id: str) -> None:
        """
        Grants viewer (read-only) access by appending a Home ID to the user's 'viewable_homes' set.
        """
        try:
            collection_name = self.schema_registry.get_collection_name("user")
            valid_id = ObjectId(user_id) if ObjectId.is_valid(user_id) else user_id
            
            # Use $addToSet to prevent duplicate authorizations
            result = self.db[collection_name].update_one(
                {"_id": valid_id},
                {
                    "$addToSet": {"data.viewable_homes": dt_id},
                    "$set": {"metadata.updated_at": datetime.utcnow()}
                }
            )
            if result.matched_count == 0:
                raise ValueError("Target user not found.")
        except Exception as e:
            raise Exception(f"Error executing viewer authorization: {str(e)}")

    def remove_viewable_home(self, user_id: str, dt_id: str) -> None:
        """
        Revokes viewer access by removing a Home ID from the user's 'viewable_homes' array.
        """
        try:
            collection_name = self.schema_registry.get_collection_name("user")
            valid_id = ObjectId(user_id) if ObjectId.is_valid(user_id) else user_id
            
            # The $pull operator selectively removes the element from the specified array
            result = self.db[collection_name].update_one(
                {"_id": valid_id},
                {
                    "$pull": {"data.viewable_homes": dt_id},
                    "$set": {"metadata.updated_at": datetime.utcnow()}
                }
            )
            if result.modified_count == 0:
                raise ValueError("Viewer not found or home environment is not currently associated.")
        except ValueError as ve:
            raise ve
        except Exception as e:
            raise Exception(f"Error revoking viewer access: {str(e)}")

    # ==============================================================================
    # 13. GLOBAL HOME REMOVAL (CASCADE DELETE)
    # ==============================================================================
    def remove_home_from_all_users(self, dt_id: str) -> None:
        """
        Executes a global cleanup when a Home Environment is annihilated. 
        Iterates over ALL user documents and forcefully strips the target ID 
        from both ownership and viewership arrays.
        """
        try:
            collection_name = self.schema_registry.get_collection_name("user")
            
            # Update all documents asynchronously by executing a widespread array modification
            self.db[collection_name].update_many(
                {}, 
                {
                    "$pull": {
                        "data.owned_homes": dt_id,
                        "data.viewable_homes": dt_id
                    }
                }
            )
        except Exception as e:
            raise Exception(f"Error during global environment cleanup cascade: {str(e)}") 

               
    # ==============================================================================
    # 14. IDENTITY & USER MANAGEMENT
    # ==============================================================================
    
    def _init_users_collection(self) -> None:
        """
        Validates the initialization of the 'user_collection' and ensures 
        cryptographic indexing constraints (e.g., unique username enforcement).
        """
        try:
            # Dynamically retrieve the specific collection name mapping via the SchemaRegistry
            collection_name = self.schema_registry.get_collection_name("user")
            
            if collection_name not in self.db.list_collection_names():
                self.db.create_collection(collection_name)
                
            # The unique index constraint is directed strictly at 'profile.username' as defined in user.yaml
            self.db[collection_name].create_index("profile.username", unique=True)
        except Exception as e:
            print(f"[WARNING] Error during the initialization of the users collection: {str(e)}")

    def get_user_by_username(self, username: str) -> Optional[Dict]:
        """
        Retrieves user document data strictly via their registered username.
        Primarily utilized during authentication layers and granting Viewer permissions.
        """
        try:
            collection_name = self.schema_registry.get_collection_name("user")
            # Query updated to traverse the nested 'profile' object structure
            return self.db[collection_name].find_one({"profile.username": username})
        except Exception as e:
            raise Exception(f"Error querying user by username: {str(e)}")

    def get_user_by_id(self, user_id: str) -> Optional[Dict]:
        """
        Retrieves a user document utilizing their unique MongoDB BSON ID.
        """
        try:
            collection_name = self.schema_registry.get_collection_name("user")
            valid_id = ObjectId(user_id) if ObjectId.is_valid(user_id) else user_id
            return self.db[collection_name].find_one({"_id": valid_id})
        except Exception as e:
            raise Exception(f"Error querying user by unique ID: {str(e)}")