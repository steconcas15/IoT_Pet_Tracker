from typing import Dict, List, Optional, Any
from pymongo import MongoClient
from datetime import datetime
from src.virtualization.digital_replica.schema_registry import SchemaRegistry
from bson import ObjectId

class DatabaseService:

    """
    Service responsible for managing MongoDB connections and handling CRUD operations
    for Digital Replicas (DRs). It dynamically resolves collections and validation
    rules using a SchemaRegistry.
    """

    # ==============================================================================
    # 1. CONSTRUCTOR & SETUP
    # ==============================================================================
    
    def __init__(
        self, connection_string: str, db_name: str, schema_registry: SchemaRegistry
    ):

        """
        Initializes the database service.
        
        Integration Note in app.py:
            This is instantiated in the main workflow using:
            - connection_string: derived from ConfigLoader.build_connection_string ("mongodb://localhost:27017")
            - db_name: loaded from db_config["settings"]["name"] ("pet_tracker_db")
            - schema_registry: the active global registry holding digital replica schemas
        """
        
        self.connection_string = connection_string
        self.db_name = db_name
        self.schema_registry = schema_registry
        # Active PyMongo client (assigned upon calling connect())
        self.client = None
        # Target MongoDB database reference
        self.db = None

    # ==============================================================================
    # 2. ESTABLISH CONNECTION
    # ==============================================================================
    def connect(self) -> None:
        """
        Establishes an active connection to the MongoDB cluster.
        """
        try:
            self.client = MongoClient(self.connection_string)
            self.db = self.client[self.db_name]
        except Exception as e:
            raise ConnectionError(f"Failed to connect to MongoDB: {str(e)}")

    # ==============================================================================
    # 3. TERMINATE CONNECTION
    # ==============================================================================            
    def disconnect(self) -> None:
        """
        Safely closes the active MongoDB connection and resets the state.
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
        Checks whether both client and database connections are ready.
        """
        return self.client is not None and self.db is not None

    # ==============================================================================
    # 5. CREATE: SAVE DIGITAL REPLICA
    # ==============================================================================
    def save_dr(self, dr_type: str, dr_data: Dict) -> str:
        """
        Saves a new Digital Replica to its designated MongoDB collection.

        The target collection name is dynamically fetched from the SchemaRegistry 
        based on the replica type.
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to MongoDB")

        try:
            # =====================================================================
            # 1 - It goes to the `src/virtualization/templates/replica.yaml` file,
            # extracts the replica name from the `type` field (`id`), and returns 
            # `replicaName_collection` (e.g., `room_collection`).
            # =====================================================================
            collection_name = self.schema_registry.get_collection_name(dr_type)
            
            # =====================================================================
            # 2 - Retrieves the Mongo structure of the replica from the `schemas{}` 
            # list, and returns an error if it is not found. 
            # =====================================================================
            validation_schema = self.schema_registry.get_validation_schema(dr_type)

            # Dynamically select the correct collection (e.g., self.db["room_collection"])
            collection = self.db[collection_name]

            # Insert the compiled replica data (Python dict) and return its unique ID
            result = collection.insert_one(dr_data)
            return str(dr_data["_id"])
        except Exception as e:
            raise Exception(f"Failed to save Digital Replica: {str(e)}")

    # ==============================================================================
    # 6. READ: GET BY UNIQUE ID
    # ==============================================================================
    def get_dr(self, dr_type: str, dr_id: str) -> Optional[Dict]:
        """
        Retrieves a single Digital Replica document using its unique identifier (_id).
        """
        
        if not self.is_connected():
            raise ConnectionError("Not connected to MongoDB")

        try:
            # =====================================================================
            # 1 - It goes to the `src/virtualization/templates/replica.yaml` file,
            # extracts the replica name from the `type` field (`id`), and returns 
            # `replicaName_collection` (e.g., `room_collection`).
            # =====================================================================
            collection_name = self.schema_registry.get_collection_name(dr_type)

            # Retrieve the replica using the collection name and its _id filed
            return self.db[collection_name].find_one({"_id": dr_id})
        except Exception as e:
            raise Exception(f"Failed to get Digital Replica: {str(e)}")

    # ==============================================================================
    # 7. READ: QUERY MULTIPLE REPLICAS
    # ==============================================================================
    def query_drs(self, dr_type: str, query: Dict = None) -> List[Dict]:
        """
        Queries the database for Digital Replicas of a specific type.
        Returns a list of documents matching the search filter criteria.
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to MongoDB")

        try:
            # =====================================================================
            # 1 - It goes to the `src/virtualization/templates/replica.yaml` file,
            # extracts the replica name from the `type` field (`id`), and returns 
            # `replicaName_collection` (e.g., `room_collection`).
            # =====================================================================
            collection_name = self.schema_registry.get_collection_name(dr_type)
            return list(self.db[collection_name].find(query or {}))
        except Exception as e:
            raise Exception(f"Failed to query Digital Replicas: {str(e)}")

    # ==============================================================================
    # 8. UPDATE: MODIFY EXISTING DIGITAL REPLICA
    # ==============================================================================
    def update_dr(self, dr_type: str, dr_id: str, update_data: Dict) -> None:
        """
        Updates an existing Digital Replica document.
        Automatically attaches or updates the metadata's 'updated_at' timestamp in UTC.
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to MongoDB")

        try:
            collection_name = self.schema_registry.get_collection_name(dr_type)

            # Ensure metadata sub-document exists and update its timestamp
            if "metadata" not in update_data:
                update_data["metadata"] = {}
            update_data["metadata"]["updated_at"] = datetime.utcnow()

            # Execute the partial update using MongoDB's $set operator
            result = self.db[collection_name].update_one(
                {"_id": dr_id}, {"$set": update_data}
            )

            # Raise an error if no document matched the target identifier
            if result.matched_count == 0:
                raise ValueError(f"Digital Replica not found: {dr_id}")

        except Exception as e:
            raise Exception(f"Failed to update Digital Replica: {str(e)}")

    # ==============================================================================
    # 9. DELETE: REMOVE RECORD
    # ==============================================================================
    def delete_dr(self, dr_type: str, dr_id: str) -> None:
        """
        Deletes a single Digital Replica document using its unique identifier.
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to MongoDB")

        try:
            collection_name = self.schema_registry.get_collection_name(dr_type)
            result = self.db[collection_name].delete_one({"_id": dr_id})

            # Confirm a document was actually deleted
            if result.deleted_count == 0:
                raise ValueError(f"Digital Replica not found: {dr_id}")
        except Exception as e:
            raise Exception(f"Failed to delete Digital Replica: {str(e)}")


    #   ---------------------- Roba Nuova ---------------------------------------------

    # ==============================================================================
    # 10. SET THE ADMIN OF THE HOME ENVIRONMENT
    # ==============================================================================
    def set_home_admin(self, dt_id: str, user_id: str) -> None:
        """
        Record the report in the database, assigning a user as Admin.
        of a specific Digital Twin (Home Environment).
        """
        try:
            # Access a collection dedicated to relationships or permissions
            # If it does not exist, MongoDB will automatically create it upon the first insertion.
            permissions_collection = self.db["home_permissions"]

            permission_data = {
                "home_id": dt_id,
                "user_id": user_id,
                "role": "admin"
            }

            # We insert the document into the database
            permissions_collection.insert_one(permission_data)

        except Exception as e:
            raise Exception(f"Errore nel salvataggio dell'admin sul database: {str(e)}")

    # ==============================================================================
    # 11. IT DELETE THE PERMISSIONS ASSOCIATED TO THE HOME ENVIRONMENT
    #     WHEN THE LATTER IS DELATED
    # ==============================================================================
    def remove_home_permissions(self, dt_id: str) -> None:
        """
        Delete all permissions (Admin and Viewer) associated with a specific Home.
        """
        try:
            self.db["home_permissions"].delete_many({"home_id": dt_id})
        except Exception as e:
            raise Exception(f"Errore nella cancellazione dei permessi: {str(e)}")


    # ==============================================================================
    # 12. SET THE ADMIN OF THE HOME ENVIRONMENT
    # ==============================================================================
    def add_home_viewer(self, dt_id: str, viewer_id: str) -> None:
        """
        Associa un utente come visualizzatore (viewer) a un Home Environment.
        """
        try:
            permissions_collection = self.db["home_permissions"]

            # 1. Controlliamo se l'utente ha già i permessi per questa casa
            existing = permissions_collection.find_one({
                "home_id": dt_id,
                "user_id": viewer_id
            })

            if existing:
                raise ValueError("Questo utente è già associato a questa casa!")

            # 2. Creiamo il nuovo permesso con ruolo 'viewer'
            permission_data = {
                "home_id": dt_id,
                "user_id": viewer_id,
                "role": "viewer"
            }

            permissions_collection.insert_one(permission_data)

        except ValueError as ve:
            # Rilanciamo l'errore di validazione (duplicato)
            raise ve
        except Exception as e:
            raise Exception(f"Errore nell'aggiunta del visualizzatore al DB: {str(e)}")

    # 4
    def remove_home_viewer(self, dt_id: str, viewer_id: str) -> None:
        """
        Rimuove il ruolo di visualizzatore (viewer) di un utente specifico da una Home.
        """
        try:
            permissions_collection = self.db["home_permissions"]

            # Eseguiamo una cancellazione mirata sul match di home_id, user_id e ruolo viewer
            result = permissions_collection.delete_one({
                "home_id": dt_id,
                "user_id": viewer_id,
                "role": "viewer"
            })

            # Se non ha cancellato nulla, significa che l'utente non era un viewer di quella casa
            if result.deleted_count == 0:
                raise ValueError("Visualizzatore non trovato o l'utente non ha questo ruolo per questa casa.")

        except ValueError as ve:
            raise ve
        except Exception as e:
            raise Exception(f"Errore nella rimozione del visualizzatore dal DB: {str(e)}")
