# ==============================================================================
# SYSTEM & THIRD-PARTY IMPORTS
# ==============================================================================
# Dict, List, Optional: Standard typing utilities used for explicit Python type hinting
from typing import Dict, List, Type, Any
# Import the BaseService template so this new service can inherit from it
from src.services.base import BaseService
# datetime: Used to generate accurate UTC timestamps for creation and update metadata
from datetime import datetime

# ==============================================================================
#                         CORE DIGITAL TWIN CLASS
# ==============================================================================
class DigitalTwin:
    """
    Core Digital Twin (DT) management class.
    Acts as the central coordinator, mapping digital replicas (DRs)
    to active services that process their data.
    """

    # ==========================================================================
    # METHOD: __init__
    # ==========================================================================
    def __init__(self):

        # List holding all Digital Replicas registered in this Twin
        self.digital_replicas: List = []

        # Dictionary mapping active service names to their instances
        # E.g., {"anomaly_detection": AnomalyDetectionService()}
        self.active_services: Dict = {}

    # ==========================================================================
    # METHOD: add_digital_replica
    # ==========================================================================
    def add_digital_replica(self, dr_instance: Any) -> None:
        """
        Adds a new Digital Replica (DR) to the Digital Twin.
        
        :param dr_instance: The replica instance to add (object or dict).
        """
        self.digital_replicas.append(dr_instance)

    # ==========================================================================
    # METHOD: add_service
    # ==========================================================================
    def add_service(self, service):
        """
        Registers and activates a service within the Digital Twin.
        Accepts either an already instantiated service or the class itself.
        
        :param service: Service instance or service class reference.
        """
        if isinstance(service, type):
            # If a class is passed (e.g., MyService) instead of an instance,
            # we instantiate it dynamically here.
            service = service()

        # Register the service using its 'name' attribute as the unique key
        self.active_services[service.name] = service

    # ==========================================================================
    # METHOD: list_services
    # ==========================================================================
    def list_services(self):
        """
        Returns a list of names of all services currently active in the DT.
        
        :return: List of service name strings.
        """
        return list(self.active_services.keys())

    # ==========================================================================
    # METHOD: remove_service
    # ==========================================================================
    def remove_service(self, service_name: str) -> None:
        """
        Removes (deactivates) an active service from the Digital Twin by name.
        
        :param service_name: The name of the service to remove.
        """
        if service_name in self.active_services:
            del self.active_services[service_name]

    # ==========================================================================
    # METHOD: get_dt_data
    # ==========================================================================
    def get_dt_data(self):
        """
        Retrieves the data of the Digital Twin, including all its DRs.
        
        :return: A dictionary containing the list of digital replicas.
        """
        return {"digital_replicas": self.digital_replicas}

    # ==========================================================================
    # METHOD: execute_service
    # ==========================================================================
    def execute_service(self, service_name: str, **kwargs):
        """
        Executes a specific service by passing all registered DRs
        along with any additional custom parameters.
        
        :param service_name: Name of the registered service to run.
        :param kwargs: Additional parameters required by the service's 'execute' method.
        :raises ValueError: If the requested service is not registered.
        """
        if service_name not in self.active_services:
            raise ValueError(f"Service {service_name} not found")

        service = self.active_services[service_name]

        # Prepare the standard data payload containing all DRs
        data = {"digital_replicas": self.digital_replicas}

        # Execute the service with the payload and unpacked arguments
        return service.execute(data, **kwargs)

    # def execute_service_on_dr(self, service_name: str, dr: Any) -> Any:
    #     """
    #     Esegue un servizio sui dati di una DR
    #     """
    #     if dr not in self.digital_replicas:
    #         raise ValueError("This DR is not part of this Digital Twin")

    #     data = dr["data"]  # Assumiamo che la DR abbia un attributo data
    #     return self.execute_service(service_name, data)

    # def get_digital_replicas_by_type(self, dr_type: str):
    #     """Get all digital replicas of a specific type"""
    #     return [dr for dr in self.digital_replicas if dr['type'] == dr_type]

    # def print_replicas(self):
    #     """Print detailed information about all Digital Replicas"""
    #     print("\n" + "=" * 80)
    #     print(f"DIGITAL TWIN STATUS - Total Replicas: {len(self.digital_replicas)}")
    #     print("=" * 80)
    #
    #     for idx, dr in enumerate(self.digital_replicas, 1):
    #         print(f"\n{idx}. DIGITAL REPLICA: {dr['type'].upper()}")
    #         print("-" * 80)
    #
    #         # Print ID and Profile
    #         print(f"ID: {dr['id']}")
    #         print("\nPROFILE:")
    #         for key, value in dr['profile'].items():
    #             print(f"  {key}: {value}")
    #
    #         # Print Metadata
    #         print("\nMETADATA:")
    #         for key, value in dr['metadata'].items():
    #             if isinstance(value, datetime):
    #                 value = value.strftime("%Y-%m-%d %H:%M:%S")
    #             print(f"  {key}: {value}")
    #
    #         # Print Data
    #         print("\nDATA:")
    #         data = dr['data']
    #         for key, value in data.items():
    #             if key == 'measurements':
    #                 print("  measurements:")
    #                 for m in value:
    #                     timestamp = m['timestamp']
    #                     if isinstance(timestamp, datetime):
    #                         timestamp = timestamp.strftime("%Y-%m-%d %H:%M:%S")
    #                     print(f"    - type: {m['measure_type']}")
    #                     print(f"      value: {m['value']}")
    #                     print(f"      timestamp: {timestamp}")
    #             elif isinstance(value, dict):
    #                 print(f"  {key}:")
    #                 for k, v in value.items():
    #                     print(f"    {k}: {v}")
    #             elif isinstance(value, list):
    #                 print(f"  {key}: {', '.join(map(str, value))}")
    #             else:
    #                 print(f"  {key}: {value}")
    #
    #         print("-" * 80)
    #
    #     print("\n" + "=" * 80 + "\n")
