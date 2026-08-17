"""
Pet Statistics Analytics Service
================================
This module defines a specialized computational service responsible for tracking, 
aggregating, and persisting behavioral metrics for pet entities. It implements 
a 30-day sliding window algorithm to maintain chronological records of area 
violations and associated deterrent (buzzer) durations.
"""

from typing import Dict, Any
from datetime import datetime, timezone
from src.services.base import BaseService

class PetStatisticsService(BaseService):
    """
    Analytical service designed to calculate daily pet statistics.
    It automatically aggregates real-time telemetry (violations and active buzzer durations)
    into daily buckets, maintaining a rolling historical ledger limited to the last 30 days.
    """

    def __init__(self):
        """
        Initializes the service and registers its nominal identifier for the 
        Digital Twin orchestration layer.
        """
        super().__init__()
        self.name = "PetStatisticsService"

    def execute(self, data: Dict, dr_type: str = "pet", attribute: str = None) -> Any:
        """
        Executes the statistical aggregation algorithm.
        
        Args:
            data (Dict): The payload containing dependency references and telemetry data.
                         Requires 'db_service', 'pet_id', 'duration_minutes', and 'violations_to_add'.
            dr_type (str, optional): The target replica classification. Defaults to "pet".
            attribute (str, optional): Unused targeted property parameter.
            
        Returns:
            Any: The fully updated 30-day statistical array.
            
        Raises:
            ValueError: If critical identifiers or database services are missing from the payload,
                        or if the requested replica does not exist.
        """
        db_service = data.get("db_service") 
        pet_id = data.get("pet_id") 
        duration_minutes = float(data.get("duration_minutes", 0.0)) 
        violations_to_add = int(data.get("violations_to_add", 1)) 

        # Validate mandatory structural dependencies
        if not db_service or not pet_id:
            raise ValueError("db_service and pet_id are strictly required to update pet statistics.") 

        pet_dr = db_service.get_dr(dr_type=dr_type, dr_id=pet_id) 
        if not pet_dr:
            raise ValueError(f"Pet with ID {pet_id} not found.") 

        # 1. Normalize the current timestamp to midnight UTC to ensure consistent daily bucketing
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) 
        
        pet_data = pet_dr.get("data", {}) 
        daily_buzzer_stats = pet_data.get("daily_buzzer_stats", []) 

        is_today = False
        current_daily_stat = None

        # 2. Evaluate chronological continuity: check if a statistical record already exists for the CURRENT day
        if daily_buzzer_stats:
            # We assume the array is sorted chronologically descending; evaluate the head element
            last_stat = daily_buzzer_stats[0] 
            stat_date = last_stat.get("date") 
            
            # Type-safe date evaluation: handles BSON dicts, native strings, or datetime objects
            if isinstance(stat_date, dict) and "$date" in stat_date:
                if stat_date["$date"].startswith(today.strftime("%Y-%m-%d")):
                    is_today = True
            elif isinstance(stat_date, datetime) and stat_date.date() == today.date(): 
                is_today = True 
            elif isinstance(stat_date, str) and stat_date.startswith(today.strftime("%Y-%m-%d")): 
                is_today = True 

            if is_today:
                current_daily_stat = last_stat 

        # 3. Application Logic: Mutate existing daily bucket or append a new temporal node
        if current_daily_stat:
            # Increment the cumulative metrics for the ongoing daily session
            current_daily_stat["auto_violations_count"] += violations_to_add 
            current_daily_stat["auto_duration_mins"] += duration_minutes 
        else:
            # Provision a new temporal bucket for the current day and prepend it to the ledger head
            new_stat = {
                "date": today,
                "auto_duration_mins": duration_minutes,
                "auto_violations_count": violations_to_add
            }
            daily_buzzer_stats.insert(0, new_stat)

        # 4. Memory/Storage constraint: Enforce the 30-day historical sliding window 
        # (truncate the array if it exceeds the boundary)
        daily_buzzer_stats = daily_buzzer_stats[:30]

        # 5. Database Synchronization: Persist the mutated ledger back to the target Digital Replica
        update_payload = {
            "data.daily_buzzer_stats": daily_buzzer_stats
        }
        db_service.update_dr(dr_type=dr_type, dr_id=pet_id, update_data=update_payload) 

        return daily_buzzer_stats