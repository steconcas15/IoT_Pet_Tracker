from abc import ABC, abstractmethod
from typing import Any, Dict

# ==============================================================================
# ABC means "Abstract Base Class". 
# This class is just a template/blueprint. You cannot run it directly.
# ==============================================================================

class BaseService(ABC):
    """Base class for all services in the pool"""

    def __init__(self):
        """
        This runs automatically when a new service is created.
        Automatically get the class name as a string.
        For example: if the class is called "WeatherService", self.name becomes "WeatherService".
        """
        self.name = self.__class__.__name__

    @abstractmethod
    def execute(self, data: Dict, dr_type: str = None, attribute: str = None) -> Any:
       """
        Every service must implement this method to process its data.
        
        Args:
            data: The main input data (usually a dictionary).
            dr_type: The type of Digital Replica (optional).
            attribute: A specific field or property to work on (optional).
            
        Returns:
            The final processed data (can be anything).
        """
        # "pass" is just a placeholder. It means "do nothing here".
        # The real code will be written inside the specific services.
        
        pass
