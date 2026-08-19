"""
Digital Twin Factory Module
===========================
This module implements the Factory Design Pattern to manage the lifecycle of 
Digital Twin (DT) entities. It handles the instantiation, configuration, and 
persistence of Digital Twins, acting as an orchestration layer between the 
in-memory Python objects and the MongoDB database. 

It dynamically binds Digital Replicas (DRs) and computational services to the 
core Digital Twin architecture.
"""

# ==============================================================================
# SYSTEM & THIRD-PARTY IMPORTS
# ==============================================================================

# Standard typing utilities used for explicit Python type hinting to ensure code robustness
from typing import Dict, List, Optional
# Used to generate accurate UTC timestamps for document creation and update metadata
from datetime import datetime
# MongoDB BSON utility used to generate cryptographically safe, unique database identifiers
from bson import ObjectId

# ==============================================================================
# LOCAL PROJECT IMPORTS (APPLICATION MODULES)
# ==============================================================================
# Coordinates raw MongoDB connections and handles direct document queries
from src.services.database_service import DatabaseService
# Manages data schemas and ensures Digital Replicas follow expected YAML/JSON structures
from src.virtualization.digital_replica.schema_registry import SchemaRegistry
# The core class instantiated in-memory to hold active replicas and executing services
from src.digital_twin.core import DigitalTwin


class DTFactory:
    """
    Factory class responsible for creating, configuring, and assembling
    fully initialized Digital Twin (DT) instances. It achieves this by pulling 
    and linking referenced Digital Replicas (DRs) and Services from the database,
    hydrating them into active in-memory objects.
    """

    # ==============================================================================
    # 1. CONSTRUCTOR & INITIALIZATION
    # ==============================================================================
    def __init__(self, db_service: DatabaseService, schema_registry: SchemaRegistry):
        """
        Initializes the factory dependency injection with database and schema management services.
        Immediately enforces database integrity by ensuring required collections and indexes exist.

        Args:
            db_service (DatabaseService): The active database connection manager.
            schema_registry (SchemaRegistry): The validator for replica structures.
        """
        # Persist reference to the database connection service
        self.db_service = db_service

        # Persist reference to the schema registry for future validation protocols
        self.schema_registry = schema_registry

        # Execute internal bootstrapping to guarantee MongoDB collection readiness
        self._init_dt_collection()


    # ==============================================================================
    # 2. INTERNAL SETUP: DATABASE INITIALIZATION
    # ==============================================================================

    def _init_dt_collection(self) -> None:
        """
        Ensures the 'digital_twins' collection exists within the MongoDB cluster.
        Establishes unique and performance-optimized indexes to accelerate queries.
        
        Raises:
            ConnectionError: If the underlying database client is unreachable.
            Exception: If collection creation or indexing fails.
        """
        # Halt execution gracefully if the database client is disconnected
        if not self.db_service.is_connected():
            raise ConnectionError("Database service is currently not connected.")

        try:
            # Retrieve the active database instance
            db = self.db_service.db

            # Create the 'digital_twins' collection if it is absent from the registry
            if "digital_twins" not in db.list_collection_names():
                db.create_collection("digital_twins")
                dt_collection = db["digital_twins"]

                # Enforce a unique index on the 'name' field to prevent twin duplication
                dt_collection.create_index("name", unique=True)
                
                # Create performance indexes on temporal metadata for chronological sorting
                dt_collection.create_index("metadata.created_at")
                dt_collection.create_index("metadata.updated_at")
                
        except Exception as e:
            raise Exception(f"Failed to initialize Digital Twin collection: {str(e)}")

    # ==============================================================================
    # 3. CREATE: NEW DIGITAL TWIN RECORD
    # ==============================================================================
    
    def create_dt(self, name: str, description: str = "") -> str:
        """
        Provisions a new Digital Twin entity in the database architecture.

        Args:
            name (str): The unique identifier name of the Digital Twin.
            description (str, optional): A contextual description of the environment. Defaults to "".

        Returns:
            str: The stringified BSON ObjectId of the newly created Digital Twin.
        """
        # Structure the document payload strictly adhering to the defined database schema
        dt_data = {
            "_id": str(ObjectId()),                      # Unique Primary Key
            "name": name,                                # Unique nominal identifier
            "description": description,                  # Contextual text
            "digital_replicas": [],                      # Array of DR polymorphic references: {"type": ..., "id": ...}
            "services": [],                              # Array of linked analytical services
            "metadata": {
                "created_at": datetime.utcnow(),         # Immutable creation timestamp (UTC)
                "updated_at": datetime.utcnow(),         # Mutable modification timestamp (UTC)
                "status": "active",                      # Default operational lifecycle state
            },
        }

        try:
            # Interface with the digital_twins collection
            dt_collection = self.db_service.db["digital_twins"]

            # Persist the structured document into MongoDB
            result = dt_collection.insert_one(dt_data)

            # Return the database-generated ID
            return str(result.inserted_id)
            
        except Exception as e:
            raise Exception(f"Failed to provision Digital Twin: {str(e)}")

    # ==============================================================================
    # 4. ASSOCIATE: ADD DIGITAL REPLICA REFERENCE
    # ==============================================================================
    
    def add_digital_replica(self, dt_id: str, dr_type: str, dr_id: str) -> None:
        """
        Validates the existence of a Digital Replica (DR) and establishes a bidirectional 
        linkage by injecting its reference into the parent Digital Twin document.

        Args:
            dt_id (str): The ID of the parent Digital Twin.
            dr_type (str): The classification of the Replica (e.g., 'room', 'pet').
            dr_id (str): The unique ID of the Replica.
        """
        try:
            dt_collection = self.db_service.db["digital_twins"]

            # Query the database to guarantee referential integrity before linkage
            dr = self.db_service.get_dr(dr_type, dr_id)

            # Abort operation if the DR is phantom/nonexistent
            if not dr:
                raise ValueError(f"Digital Replica resolution failed for ID: {dr_id}")

            # Execute an atomic update operation within MongoDB
            dt_collection.update_one(
                {"_id": dt_id},                 
                {
                    # Atomically append the reference dict to the replicas array
                    "$push": {"digital_replicas": {"type": dr_type, "id": dr_id}},
                    # Synchronize the modification timestamp
                    "$set": {"metadata.updated_at": datetime.utcnow()},
                },
            )
        except Exception as e:
            raise Exception(f"Failed to link Digital Replica: {str(e)}")

    # ==============================================================================
    # 5. SERVICE MANAGEMENT: REGISTRY MAPPING
    # ==============================================================================
    
    def _get_service_module_mapping(self) -> Dict[str, str]:
        """
        Provides an internal lookup table mapping abstract Service Class names 
        to their explicit Python import paths. Crucial for dynamic class loading.

        Returns:
            Dict[str, str]: A dictionary of available analytical and computational services.
        """
        return {
            "PetDetectionService": "src.services.pet_detection_service",
            "RoomStatisticsService": "src.services.room_statistics_service",
            "PetStatisticsService": "src.services.pet_statistics_service",
        }

    # ==============================================================================
    # 6. ASSOCIATE: ADD SERVICE REFERENCE
    # ==============================================================================
    
    def add_service(
        self, dt_id: str, service_name: str, service_config: Dict = None
    ) -> None:
        """
        Dynamically validates, imports, and associates a computational service to a DT.
        Utilizes Python's reflection capabilities to ensure the service is executable 
        before committing its configuration to the database.

        Args:
            dt_id (str): The target Digital Twin ID.
            service_name (str): The designated name of the service class.
            service_config (Dict, optional): Injection parameters for the service.
        """
        try:
            dt_collection = self.db_service.db["digital_twins"]
            module_mapping = self._get_service_module_mapping()

            # Prevent injection of unregistered or malicious service requests
            if service_name not in module_mapping:
                raise ValueError(
                    f"Service '{service_name}' is not registered in the system module mapping."
                )

            # Resolve the absolute import path
            module_name = module_mapping[service_name]

            # Attempt a hot dynamic import to verify compilation and syntax integrity
            try:
                # Dynamically load the target module into memory
                service_module = __import__(module_name, fromlist=[service_name])

                # Extract the specified service class definition
                service_class = getattr(service_module, service_name)

                # Instantiate the class to validate constructor parameters
                service = service_class()

                # Construct the persistent metadata payload
                service_data = {
                    "name": service_name,                
                    "config": service_config or {},      
                    "status": "active",                  
                    "added_at": datetime.utcnow(),       
                }

                # Atomically append the service configuration to the DT document
                dt_collection.update_one(
                    {"_id": dt_id},                        
                    {
                        "$push": {"services": service_data},
                        "$set": {"metadata.updated_at": datetime.utcnow()},
                    },
                )
            except (ImportError, AttributeError) as e:
                raise ValueError(
                    f"Failed to dynamically load service '{service_name}' from module '{module_name}': {str(e)}"
                )

        except Exception as e:
            raise Exception(f"Failed to associate service: {str(e)}")

    # ==============================================================================
    # 7. READ: FETCH DATA BY ID
    # ==============================================================================
    def get_dt(self, dt_id: str) -> Optional[Dict]:
        """
        Retrieves the raw JSON/Dict representation of a Digital Twin.

        Args:
            dt_id (str): The unique ID of the Digital Twin.

        Returns:
            Optional[Dict]: The document dictionary if found, None otherwise.
        """
        try:
            dt_collection = self.db_service.db["digital_twins"]
            return dt_collection.find_one({"_id": dt_id})
        except Exception as e:
            raise Exception(f"Failed to retrieve Digital Twin: {str(e)}")

    # ==============================================================================
    # 8. READ: LIST ALL DIGITAL TWINS
    # ==============================================================================
    
    def list_dts(self) -> List[Dict]:
        """
        Fetches the complete registry of all instantiated Digital Twins.

        Returns:
            List[Dict]: A list containing all Digital Twin documents.
        """
        try:
            dt_collection = self.db_service.db["digital_twins"]
            # Convert the MongoDB cursor generator into a static Python list
            return list(dt_collection.find())
        except Exception as e:
            raise Exception(f"Failed to compile Digital Twin list: {str(e)}")


    # ==============================================================================
    # 9. INSTANTIATE: BUILD IN-MEMORY OBJECTS FROM DATABASE DATA
    # ==============================================================================
    
    def create_dt_from_data(self, dt_data: dict) -> DigitalTwin:
        """
        Hydrates a persistent database dictionary into a fully functional, 
        in-memory DigitalTwin Python object. Reconstructs all Replica bindings 
        and dynamically instantiates all associated services.

        Args:
            dt_data (dict): The raw database document representing the Twin.

        Returns:
            DigitalTwin: An active, executable representation of the Twin architecture.
        """
        print("\n=== Instantiating Digital Twin ===")
        try:
            # Step A: Initialize the core algorithmic wrapper
            dt = DigitalTwin()
            print(f"[Hydration] Initialized core instance for: {dt_data.get('name', 'Unnamed')}")

            # Step B: Resolve and mount all associated Digital Replicas
            for dr_ref in dt_data.get("digital_replicas", []):
                dr = self.db_service.get_dr(dr_ref["type"], dr_ref["id"])
                if dr:
                    dt.add_digital_replica(dr)
                    print(f"[Hydration] Successfully mounted DR: {dr_ref['type']} (ID: {dr_ref['id']})")

            # Step C: Dynamically reflect, instantiate, and configure linked computational services
            print("\n[Hydration] Bootstrapping background services...")
            service_mapping = self._get_service_module_mapping()

            for service_data in dt_data.get("services", []):
                service_name = service_data["name"]
                print(f"[Service Loader] Processing node: {service_name}")

                if service_name in service_mapping:
                    try:
                        module_name = service_mapping[service_name]
                        
                        # Reflection: Load the module string
                        service_module = __import__(module_name, fromlist=[service_name])
                        
                        # Reflection: Extract the class type
                        service_class = getattr(service_module, service_name)
                        
                        # Reflection: Instantiate the object
                        service = service_class()

                        # Inject configuration parameters if the service supports it
                        if hasattr(service, "configure") and "config" in service_data:
                            service.configure(service_data["config"])
                            print(f"[Service Loader] Configuration injected: {service_data['config']}")

                        dt.add_service(service)
                        print(f"[Service Loader] Service '{service_name}' successfully bound to Twin.")
                    except Exception as e:
                        print(f"[Service Loader] Fatal error loading '{service_name}': {str(e)}")
                else:
                    print(f"[Service Loader] Warning: '{service_name}' is orphaned or unregistered.")

            return dt

        except Exception as e:
            print(f"[Hydration Error] Process terminated: {str(e)}")
            raise Exception(f"Failed to hydrate DT from persistent data: {str(e)}")

    # ==============================================================================
    # 10. ENTRYPOINT: GET INSTANCE BY ID
    # ==============================================================================
    
    def get_dt_instance(self, dt_id: str) -> Optional[DigitalTwin]:
        """
        High-level wrapper that fetches raw data and immediately hydrates it 
        into a functional Python object.

        Args:
            dt_id (str): The ID of the target Digital Twin.

        Returns:
            Optional[DigitalTwin]: The fully assembled instance, or None if missing.
        """
        try:
            dt_data = self.get_dt(dt_id)

            if not dt_data:
                return None

            return self.create_dt_from_data(dt_data)

        except Exception as e:
            raise Exception(f"Failed to instantiate Digital Twin wrapper: {str(e)}")

    # ==============================================================================
    # 11. DELETION & CLEANUP
    # ==============================================================================

    def delete_dt(self, dt_id: str) -> None:
        """
        Permanently destroys a Digital Twin record from the database architecture.

        Args:
            dt_id (str): The ID of the Twin to annihilate.
            
        Raises:
            ValueError: If the targeted ID does not exist.
        """
        try:
            dt_collection = self.db_service.db["digital_twins"]
            result = dt_collection.delete_one({"_id": dt_id})

            if result.deleted_count == 0:
                raise ValueError(f"Deletion failed: Digital Twin ID '{dt_id}' not found.")

        except Exception as e:
            raise Exception(f"Failed to destroy Digital Twin: {str(e)}")

    def remove_digital_replica(self, dt_id: str, dr_id: str) -> None:
        """
        Severs the linkage between a parent Digital Twin and a specific Digital Replica.
        Executes a targeted atomic pull operation to remove the reference array element.
    
        Args:
            dt_id (str): The Digital Twin ID.
            dr_id (str): The targeted Digital Replica ID to disconnect.
        """
        try:
            dt_collection = self.db_service.db["digital_twins"]
    
            # Perform an atomic multi-step update
            dt_collection.update_one(
                {"_id": dt_id},
                {
                    # Safely extract the target dictionary from the array
                    "$pull": {
                        "digital_replicas": {
                            "id": dr_id
                        }
                    },
                    # Update temporal metadata
                    "$set": {
                        "metadata.updated_at": datetime.utcnow()
                    }
                }
            )
        except Exception as e:
            raise Exception(f"Failed to sever Digital Replica link: {str(e)}")