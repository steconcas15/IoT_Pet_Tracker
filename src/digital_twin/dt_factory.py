# ==============================================================================
# SYSTEM & THIRD-PARTY IMPORTS
# ==============================================================================

# Dict, List, Optional: Standard typing utilities used for explicit Python type hinting
from typing import Dict, List, Optional
# datetime: Used to generate accurate UTC timestamps for creation and update metadata
from datetime import datetime
# ObjectId: MongoDB BSON utility used to generate safe, unique database identifiers
from bson import ObjectId

# ==============================================================================
# LOCAL PROJECT IMPORTS (APPLICATION MODULES)
# ==============================================================================
# DatabaseService: Coordinates raw MongoDB connections and handles direct document queries
from src.services.database_service import DatabaseService
# SchemaRegistry: Manages data schemas and ensures Digital Replicas follow expected structures
from src.virtualization.digital_replica.schema_registry import SchemaRegistry
# DigitalTwin: The core class instantiated in-memory to hold active replicas and services
from src.digital_twin.core import DigitalTwin


class DTFactory:
    """
    Factory class responsible for creating, configuring, and assembling
    fully-initialized Digital Twin (DT) instances by pulling and linking 
    their referenced Digital Replicas (DRs) and Services from the database.
    """

    # ==============================================================================
    # 1. CONSTRUCTOR & INITIALIZATION
    # ==============================================================================
    def __init__(self, db_service: DatabaseService, schema_registry: SchemaRegistry):
        """
        Initializes the factory with database and schema management services.
        Immediately ensures the required database collections and indexes exist.
        """

        # Save reference to the database connection service
        self.db_service = db_service

        # Save reference to the schema registry for DR validation
        self.schema_registry = schema_registry

        # Call internal helper to make sure the MongoDB collection is ready
        self._init_dt_collection()


    # ==============================================================================
    # 2. INTERNAL SETUP: DATABASE INITIALIZATION
    # ==============================================================================

    def _init_dt_collection(self) -> None:
        """
        Ensures the 'digital_twins' collection exists in MongoDB.
        Sets up unique and performance indexes for lookups and queries.
        """

        # Halt execution if the database client is not connected
        if not self.db_service.is_connected():
            raise ConnectionError("Database service not connected")

        try:
            # Retrieve the active database object
            db = self.db_service.db

            # Create the 'digital_twins' collection if it does not exist yet
            if "digital_twins" not in db.list_collection_names():
                db.create_collection("digital_twins")
                # Access the newly created collection
                dt_collection = db["digital_twins"]

                # Create a unique index on 'name' to prevent duplicate twin records
                dt_collection.create_index("name", unique=True)
                
                dt_collection.create_index("metadata.created_at")
                dt_collection.create_index("metadata.updated_at")
                
        except Exception as e:
            raise Exception(f"Failed to initialize DT collection: {str(e)}")

    # ==============================================================================
    # 3. CREATE: NEW DIGITAL TWIN RECORD
    # ==============================================================================
    
    def create_dt(self, name: str, description: str = "") -> str:
        """
        Create a new Digital Twin

        Args:
            name: Name of the Digital Twin
            description: Optional description

        Returns:
            str: ID of the created Digital Twin
        """

        # Structure the document payload according to the DB schema
        dt_data = {
            "_id": str(ObjectId()),                      # Unique ID of the Digital Twin
            "name": name,                                # Unique name of the DT
            "description": description,                  # Optional text description
            "digital_replicas": [],                      # Array of DR references: {"type": ..., "id": ...}
            "services": [],                              # Array of linked services: {"name": ..., "config": ...}
            "metadata": {
                "created_at": datetime.utcnow(),         # Creation timestamp in UTC
                "updated_at": datetime.utcnow(),         # Last update timestamp in UTC
                "status": "active",                      # Initial operational status
            },
        }

        try:
            # Get reference to the digital twins collection
            dt_collection = self.db_service.db["digital_twins"]

            # Insert the structured document into the collection
            result = dt_collection.insert_one(dt_data)

            # Return the newly inserted ID converted to string
            return str(result.inserted_id)
            
        except Exception as e:
            raise Exception(f"Failed to create Digital Twin: {str(e)}")

    # ==============================================================================
    # 4. ASSOCIATE: ADD DIGITAL REPLICA REFERENCE
    # ==============================================================================
    
    def add_digital_replica(self, dt_id: str, dr_type: str, dr_id: str) -> None:
        """
        Verifies that a Digital Replica exists, then links its reference (type + ID)
        to the target Digital Twin document.
        """
        try:
            # Get reference to the collection to perform the update
            dt_collection = self.db_service.db["digital_twins"]

            # Query the DB to ensure the DR actually exists before saving the link
            dr = self.db_service.get_dr(dr_type, dr_id)

            # If the DR is not found, stop the operation to prevent orphan references
            if not dr:
                raise ValueError(f"Digital Replica not found: {dr_id}")

            # Perform an atomic document update in MongoDB
            dt_collection.update_one(
                {"_id": dt_id},                 # Filter the specific DT by its ID
                {
                    # Push the reference dictionary into the digital_replicas array
                    "$push": {"digital_replicas": {"type": dr_type, "id": dr_id}},
                    # Update the modification timestamp of the DT to current UTC time
                    "$set": {"metadata.updated_at": datetime.utcnow()},
                },
            )
        except Exception as e:
            raise Exception(f"Failed to add Digital Replica: {str(e)}")

    # ==============================================================================
    # 5. SERVICE MANAGEMENT: REGISTRY MAPPING
    # ==============================================================================
    
    def _get_service_module_mapping(self) -> Dict[str, str]:
        """
        Internal mapping matching Service Class names to their Python import paths.
        Used to dynamically import services when building a Digital Twin.
        """
        
        # Return the registry mapping of available services in the system
        return {
            "AggregationService": "src.services.analytics",
            "TemperaturePredictionService": "src.services.TemperaturePredictionService",
        }

    # ==============================================================================
    # 6. ASSOCIATE: ADD SERVICE REFERENCE
    # ==============================================================================
    
    def add_service(
        self, dt_id: str, service_name: str, service_config: Dict = None
    ) -> None:
        """
        Validates, imports, and links an analytics/computational service to a DT.
        Ensures the service class is importable before saving its metadata.

        Args:
            dt_id: Digital Twin ID
            service_name: Name of the service
            service_config: Optional service configuration
        """
        try:

            # Retrieve the digital twins collection
            dt_collection = self.db_service.db["digital_twins"]

            # 5. - Get the mapping of registered services
            module_mapping = self._get_service_module_mapping()

            # Abort if the requested service is not registered in the mapping
            if service_name not in module_mapping:
                raise ValueError(
                    f"Service {service_name} not configured in module mapping"
                )

            # Identify the target Python module containing the service
            module_name = module_mapping[service_name]

            # Attempt a hot import to verify the code is clean and executable
            try:
                # Dynamically import the target module
                service_module = __import__(module_name, fromlist=[service_name])

                # Extract the specific service class from the imported module
                service_class = getattr(service_module, service_name)

                # Instantiate class to validate the constructor and avoid future runtime crashes
                service = service_class()

                # Build the service metadata package to be saved in the database
                service_data = {
                    "name": service_name,                # Class name of the service
                    "config": service_config or {},      # Configuration dict (defaults to empty)
                    "status": "active",                  # Operational status of the service
                    "added_at": datetime.utcnow(),       # Timestamp when the service was linked
                }

                # Save service config reference to the database record
                dt_collection.update_one(
                    {"_id": dt_id},                        # Locate the target DT
                    {
                        # Append the service metadata to the services array
                        "$push": {"services": service_data},
                        # Set the global modification timestamp
                        "$set": {"metadata.updated_at": datetime.utcnow()},
                    },
                )
            except (ImportError, AttributeError) as e:
                raise ValueError(
                    f"Failed to load service {service_name} from module {module_name}: {str(e)}"
                )

        except Exception as e:
            raise Exception(f"Failed to add service: {str(e)}")

    # ==============================================================================
    # 7. READ: FETCH DATA BY ID
    # ==============================================================================
    def get_dt(self, dt_id: str) -> Optional[Dict]:
        """
        Get a Digital Twin by ID

        Args:
            dt_id: Digital Twin ID

        Returns:
            Dict: Digital Twin data if found, None otherwise
        """
        try:
            # Access the target database collection
            dt_collection = self.db_service.db["digital_twins"]

            # Query for an exact match on the '_id' field
            return dt_collection.find_one({"_id": dt_id})
        except Exception as e:
            raise Exception(f"Failed to get Digital Twin: {str(e)}")

    # ==============================================================================
    # 8. READ: LIST ALL DIGITAL TWINS
    # ==============================================================================
    
    def list_dts(self) -> List[Dict]:
        """
        List all Digital Twins

        Returns:
            List[Dict]: List of Digital Twins
        """
        try:
            # Access the digital twins collection
            dt_collection = self.db_service.db["digital_twins"]

            # Retrieve all documents (empty find) and convert the MongoDB cursor to a Python list
            return list(dt_collection.find())
        except Exception as e:
            raise Exception(f"Failed to list Digital Twins: {str(e)}")


    # ==============================================================================
    # 9. INSTANTIATE: BUILD IN-MEMORY OBJECTS FROM DATABASE DATA
    # ==============================================================================
    
    def create_dt_from_data(self, dt_data: dict) -> DigitalTwin:
        """
        Create a DigitalTwin instance from database data with enhanced debugging
        """
        
        print("\n=== Creating DT Instance ===")
        try:
            # Create new DT instance
            # Step A: Create a fresh instance of our core DigitalTwin class
            dt = DigitalTwin()
            print(f"Created new DT instance for {dt_data.get('name', 'unnamed')}")

            # Add Digital Replicas
            # Step B: Retrieve actual DR documents and register them to the live instance
            for dr_ref in dt_data.get("digital_replicas", []):
                dr = self.db_service.get_dr(dr_ref["type"], dr_ref["id"])
                if dr:
                    dt.add_digital_replica(dr)
                    print(f"Added DR: {dr_ref['type']} - {dr_ref['id']}")

            # Add Services
            # Step C: Dynamically import, configure, and attach runtime services
            print("\nLoading services...")
            service_mapping = self._get_service_module_mapping()
            print(f"Service mapping: {service_mapping}")

            for service_data in dt_data.get("services", []):
                service_name = service_data["name"]
                print(f"\nProcessing service: {service_name}")

                if service_name in service_mapping:
                    try:
                        module_name = service_mapping[service_name]
                        print(f"Loading module: {module_name}")

                        service_module = __import__(
                            module_name, fromlist=[service_name]
                        )
                        print(f"Module loaded successfully")

                        service_class = getattr(service_module, service_name)
                        print(f"Got service class: {service_class}")

                        service = service_class()
                        print(f"Service instance created")

                        if hasattr(service, "configure") and "config" in service_data:
                            service.configure(service_data["config"])
                            print(f"Service configured with: {service_data['config']}")

                        dt.add_service(service)
                        print(f"Service added to DT")
                        print(f"Current DT services: {dt.list_services()}")
                    except Exception as e:
                        print(f"Error adding service {service_name}: {str(e)}")
                        print(f"Exception type: {type(e)}")
                else:
                    print(f"Warning: Service {service_name} not found in mapping")

            return dt

        except Exception as e:
            print(f"Error creating DT: {str(e)}")
            print(f"Exception type: {type(e)}")
            raise Exception(f"Failed to create DT from data: {str(e)}")

    # ==============================================================================
    # 10. ENTRYPOINT: GET INSTANCE BY ID
    # ==============================================================================
    
    def get_dt_instance(self, dt_id: str) -> Optional[DigitalTwin]:
        """
        Get a fully initialized DigitalTwin instance by ID

        Args:
            dt_id: Digital Twin ID

        Returns:
            Optional[DigitalTwin]: Digital Twin instance if found, None otherwise
        """
        try:
            # Get DT data from database
            dt_data = self.get_dt(dt_id)

            # If no document matches the provided ID, return None
            if not dt_data:
                return None

            # Create and return DT instance
            return self.create_dt_from_data(dt_data)

        except Exception as e:
            raise Exception(f"Failed to get DT instance: {str(e)}")


    # def get_dt_by_name(self, name: str) -> Optional[Dict]:
    #     """
    #     Get a Digital Twin by name
    #
    #     Args:
    #         name: Digital Twin name
    #
    #     Returns:
    #         Dict: Digital Twin data if found, None otherwise
    #     """
    #     try:
    #         dt_collection = self.db_service.db["digital_twins"]
    #         return dt_collection.find_one({"name": name})
    #     except Exception as e:
    #         raise Exception(f"Failed to get Digital Twin: {str(e)}")


    # def update_dt(self, dt_id: str, update_data: Dict) -> None:
    #     """
    #     Update a Digital Twin
    #
    #     Args:
    #         dt_id: Digital Twin ID
    #         update_data: Data to update
    #     """
    #     try:
    #         dt_collection = self.db_service.db["digital_twins"]
    #
    #         # Ensure metadata.updated_at is set
    #         if "metadata" not in update_data:
    #             update_data["metadata"] = {}
    #         update_data["metadata"]["updated_at"] = datetime.utcnow()
    #
    #         result = dt_collection.update_one(
    #             {"_id": dt_id},
    #             {"$set": update_data}
    #         )
    #
    #         if result.matched_count == 0:
    #             raise ValueError(f"Digital Twin not found: {dt_id}")
    #
    #     except Exception as e:
    #         raise Exception(f"Failed to update Digital Twin: {str(e)}")

    def delete_dt(self, dt_id: str) -> None:
        """
        Delete a Digital Twin

        Args:
            dt_id: Digital Twin ID
        """
        try:
            dt_collection = self.db_service.db["digital_twins"]
            result = dt_collection.delete_one({"_id": dt_id})

            if result.deleted_count == 0:
                raise ValueError(f"Digital Twin not found: {dt_id}")

        except Exception as e:
            raise Exception(f"Failed to delete Digital Twin: {str(e)}")

    def remove_digital_replica(self, dt_id: str, dr_id: str) -> None:
        """
        Remove a Digital Replica reference from a Digital Twin
    
        Args:
            dt_id: Digital Twin ID
            dr_id: Digital Replica ID
        """
        try:
            dt_collection = self.db_service.db["digital_twins"]
    
            dt_collection.update_one(
                {"_id": dt_id},
                {
                    "$pull": {
                        "digital_replicas": {
                            "id": dr_id
                        }
                    },
                    "$set": {
                        "metadata.updated_at": datetime.utcnow()
                    }
                }
            )
        except Exception as e:
            raise Exception(f"Failed to remove Digital Replica: {str(e)}")

    # def remove_service(self, dt_id: str, service_name: str) -> None:
    #     """
    #     Remove a service reference from a Digital Twin
    #
    #     Args:
    #         dt_id: Digital Twin ID
    #         service_name: Name of the service to remove
    #     """
    #     try:
    #         dt_collection = self.db_service.db["digital_twins"]
    #
    #         dt_collection.update_one(
    #             {"_id": dt_id},
    #             {
    #                 "$pull": {
    #                     "services": {
    #                         "name": service_name
    #                     }
    #                 },
    #                 "$set": {
    #                     "metadata.updated_at": datetime.utcnow()
    #                 }
    #             }
    #         )
    #     except Exception as e:
    #         raise Exception(f"Failed to remove service: {str(e)}")
