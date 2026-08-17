"""
Abstract Service Interface Module
=================================
This module defines the foundational abstract base class (ABC) for all 
computational and analytical services within the Digital Twin architecture. 
It enforces a uniform interface (contract) across all concrete service 
implementations, promoting polymorphism and adherence to the Open/Closed 
Principle of SOLID software design.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict


# ==============================================================================
#                      ABSTRACT BASE CLASS DEFINITION
# ==============================================================================

class BaseService(ABC):
    """
    Abstract Base Class (ABC) serving as the architectural blueprint for all 
    functional services in the execution pool. As an abstract entity, it cannot 
    be instantiated directly; it mandates that all derived concrete subclasses 
    implement the defined abstract methods.
    """

    def __init__(self):
        """
        Initializes the abstract service state.
        
        Employs Python's internal reflection capabilities (`__class__.__name__`) 
        to automatically extract and assign the concrete subclass's identifier 
        to the `name` attribute upon instantiation. This facilitates dynamic 
        service routing and registry management within the core Digital Twin 
        orchestration layer.
        """
        self.name = self.__class__.__name__

    @abstractmethod
    def execute(self, data: Dict, dr_type: str = None, attribute: str = None) -> Any:
        """
        Abstract execution contract. Every concrete service inheriting from 
        BaseService MUST override and implement this method to encapsulate its 
        specific algorithmic logic for processing telemetry or state data.

        Args:
            data (Dict): The primary structural payload (typically containing the 
                         Digital Replicas state dictionary).
            dr_type (str, optional): The specific classification of Digital Replica targeted.
            attribute (str, optional): A targeted property or field for localized processing.

        Returns:
            Any: The computed output, mutated state, or analytical result derived 
                 from the concrete implementation.

        Raises:
            NotImplementedError: Implicitly raised by the Python ABC meta-class 
                                 if a subclass fails to override this definition.
        """
        # Execution logic is strictly deferred to concrete subclasses.
        pass