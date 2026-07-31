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


    # ==============================================================================
    # 10. VERIFICA RUOLI (ADMIN / VIEWER)
    # ==============================================================================
    def is_home_admin(self, dt_id: str, user_id: str) -> bool:
        """Verifica se l'ID della casa è nell'array owned_homes dell'utente."""
        try:
            collection_name = self.schema_registry.get_collection_name("user")
            valid_id = ObjectId(user_id) if ObjectId.is_valid(user_id) else user_id
            
            # Cerca l'utente che ha questo ID e che possiede questa specifica casa
            user = self.db[collection_name].find_one({
                "_id": valid_id,
                "data.owned_homes": dt_id
            })
            return user is not None
        except Exception as e:
            raise Exception(f"Errore durante la verifica dei permessi admin: {str(e)}")

    # ==============================================================================
    # 12. GESTIONE CASE IN VISUALIZZAZIONE (VIEWABLE HOMES)
    # ==============================================================================
    def add_viewable_home(self, user_id: str, dt_id: str) -> None:
        """Aggiunge una casa alle viewable_homes dell'utente (Ruolo Viewer)."""
        try:
            collection_name = self.schema_registry.get_collection_name("user")
            valid_id = ObjectId(user_id) if ObjectId.is_valid(user_id) else user_id
            
            result = self.db[collection_name].update_one(
                {"_id": valid_id},
                {
                    "$addToSet": {"data.viewable_homes": dt_id},
                    "$set": {"metadata.updated_at": datetime.utcnow()}
                }
            )
            if result.matched_count == 0:
                raise ValueError("Utente non trovato.")
        except Exception as e:
            raise Exception(f"Errore nell'aggiunta del viewer: {str(e)}")

    def remove_viewable_home(self, user_id: str, dt_id: str) -> None:
        """Rimuove una casa dalle viewable_homes dell'utente."""
        try:
            collection_name = self.schema_registry.get_collection_name("user")
            valid_id = ObjectId(user_id) if ObjectId.is_valid(user_id) else user_id
            
            # $pull rimuove l'elemento dall'array
            result = self.db[collection_name].update_one(
                {"_id": valid_id},
                {
                    "$pull": {"data.viewable_homes": dt_id},
                    "$set": {"metadata.updated_at": datetime.utcnow()}
                }
            )
            if result.modified_count == 0:
                raise ValueError("Viewer non trovato o casa non associata.")
        except ValueError as ve:
            raise ve
        except Exception as e:
            raise Exception(f"Errore nella rimozione del viewer: {str(e)}")

    # ==============================================================================
    # 13. RIMOZIONE GLOBALE CASA (CASCADE DELETE)
    # ==============================================================================
    def remove_home_from_all_users(self, dt_id: str) -> None:
        """Quando una casa viene eliminata, la rimuove dagli array di TUTTI gli utenti."""
        try:
            collection_name = self.schema_registry.get_collection_name("user")
            
            # Aggiorna tutti i documenti togliendo l'ID da entrambi gli array
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
            raise Exception(f"Errore nella pulizia globale della casa: {str(e)}") 

               
    # # ==============================================================================
    # 14. IDENTITY & USER MANAGEMENT
    # ==============================================================================
    
    def _init_users_collection(self) -> None:
        """
        Assicura che la collezione 'user_collection' esista e che l'username sia univoco.
        """
        try:
            # Recupera dinamicamente il nome della collezione usando lo SchemaRegistry
            collection_name = self.schema_registry.get_collection_name("user")
            
            if collection_name not in self.db.list_collection_names():
                self.db.create_collection(collection_name)
                
            # L'indice univoco ora deve puntare a 'profile.username' secondo user.yaml
            self.db[collection_name].create_index("profile.username", unique=True)
        except Exception as e:
            print(f"[WARNING] Errore nell'inizializzazione della collezione utenti: {str(e)}")

    def get_user_by_username(self, username: str) -> Optional[Dict]:
        """
        Recupera i dati di un utente tramite il suo username (usato per Login e aggiunta Viewer).
        """
        try:
            collection_name = self.schema_registry.get_collection_name("user")
            # Aggiornato per cercare l'username all'interno dell'oggetto profile
            return self.db[collection_name].find_one({"profile.username": username})
        except Exception as e:
            raise Exception(f"Errore nel recupero dell'utente: {str(e)}")

    def get_user_by_id(self, user_id: str) -> Optional[Dict]:
        """
        Recupera un utente tramite il suo ID univoco MongoDB.
        """
        try:
            collection_name = self.schema_registry.get_collection_name("user")
            valid_id = ObjectId(user_id) if ObjectId.is_valid(user_id) else user_id
            return self.db[collection_name].find_one({"_id": valid_id})
        except Exception as e:
            raise Exception(f"Errore nel recupero dell'utente: {str(e)}")
        