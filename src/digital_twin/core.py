"""
Digital Twin Core Orchestration Module
======================================
This module defines the fundamental `DigitalTwin` class, which serves as the 
central in-memory representation of a physical environment. It implements an 
orchestration layer that maps abstract Digital Replicas (DRs) to active 
computational services, facilitating data processing and simulation routing.
"""

# ==============================================================================
# SYSTEM & THIRD-PARTY IMPORTS
# ==============================================================================
# Standard typing utilities utilized for explicit Python type hinting and static analysis
from typing import Dict, List, Type, Any
# Import the BaseService interface to ensure polymorphic service execution
from src.services.base import BaseService
# Used to generate accurate UTC timestamps for temporal operations and metadata
from datetime import datetime

# ==============================================================================
#                         CORE DIGITAL TWIN CLASS
# ==============================================================================
class DigitalTwin:
    """
    Core Digital Twin (DT) management architecture.
    Acts as the central execution coordinator, aggregating discrete Digital Replicas (DRs)
    and mapping them to specialized computational services for data processing, 
    telemetry analysis, and state mutation.
    """

    # ==========================================================================
    # METHOD: __init__
    # ==========================================================================
    def __init__(self):
        """
        Initializes the stateful attributes of the Digital Twin instance.
        Allocates memory structures for replica storage and service routing.
        """
        # Array structure holding all instantiated Digital Replicas registered within this Twin context
        self.digital_replicas: List = []

        # Hash map linking active service nominal identifiers to their concrete executing instances
        # Example mapping: {"anomaly_detection": AnomalyDetectionService()}
        self.active_services: Dict = {}

    # ==========================================================================
    # METHOD: add_digital_replica
    # ==========================================================================
    def add_digital_replica(self, dr_instance: Any) -> None:
        """
        Integrates a new Digital Replica (DR) entity into the encompassing Digital Twin ecosystem.
        
        Args:
            dr_instance (Any): The initialized replica instance (object or dictionary) 
                               representing a physical counterpart (e.g., room, pet, sensor).
        """
        self.digital_replicas.append(dr_instance)

    # ==========================================================================
    # METHOD: add_service
    # ==========================================================================
    def add_service(self, service: Any) -> None:
        """
        Registers and provisions a computational service within the Digital Twin environment.
        Employs dynamic instantiation if a class reference is provided rather than an object.
        
        Args:
            service (Any): A pre-instantiated service object or an uninstantiated service class reference.
        """
        # Implement dynamic reflection: instantiate the service if passed as a strict type
        if isinstance(service, type):
            service = service()

        # Map the active instance into the routing dictionary utilizing its intrinsic 'name' property
        self.active_services[service.name] = service

    # ==========================================================================
    # METHOD: list_services
    # ==========================================================================
    def list_services(self) -> List[str]:
        """
        Retrieves the registry of all computational services currently bound to this instance.
        
        Returns:
            List[str]: An array comprising the nominal string identifiers of active services.
        """
        return list(self.active_services.keys())

    # ==========================================================================
    # METHOD: remove_service
    # ==========================================================================
    def remove_service(self, service_name: str) -> None:
        """
        Gracefully unbinds and deactivates a specific service from the Digital Twin architecture.
        
        Args:
            service_name (str): The specific string identifier of the targeted service.
        """
        # Safe deletion utilizing dictionary membership validation
        if service_name in self.active_services:
            del self.active_services[service_name]

    # ==========================================================================
    # METHOD: get_dt_data
    # ==========================================================================
    def get_dt_data(self) -> Dict[str, List]:
        """
        Compiles and exports the composite state data of the Digital Twin, 
        encapsulating all registered child Digital Replicas.
        
        Returns:
            Dict[str, List]: A structured payload containing the current digital replicas array.
        """
        return {"digital_replicas": self.digital_replicas}

    # ==========================================================================
    # METHOD: execute_service
    # ==========================================================================
    def execute_service(self, service_name: str, **kwargs) -> Any:
        """
        Triggers the polymorphic execution of a specific registered service. 
        Automatically injects the standard Digital Twin structural payload alongside 
        any arbitrary keyword arguments required for the specific algorithmic task.
        
        Args:
            service_name (str): The specific string identifier of the service to invoke.
            **kwargs: Variable keyword arguments utilized for dynamic parameter injection.
            
        Returns:
            Any: The resulting output computed by the targeted service logic.
            
        Raises:
            ValueError: If the requested service identifier is absent from the active registry.
        """
        # Enforce strict routing: abort if the targeted service is not provisioned
        if service_name not in self.active_services:
            raise ValueError(f"Execution failed: Service '{service_name}' is not registered in the active context.")

        # Retrieve the functional service instance
        service = self.active_services[service_name]

        # Construct the standardized baseline telemetry/state payload encompassing all replicas
        data = {"digital_replicas": self.digital_replicas}

        # Dispatch the payload and any unpacked dynamic arguments to the service engine
        return service.execute(data, **kwargs)