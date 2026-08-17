"""
Room Occupancy Statistics Analytics Service
===========================================
This module defines a specialized computational service responsible for tracking
and aggregating daily room occupancy metrics. It calculates the frequency of 
entries and cumulative stay durations, automatically resetting on a daily basis 
to ensure strict temporal isolation.
"""

from typing import Dict, Any
from datetime import datetime, timezone
from src.services.base import BaseService

class RoomStatisticsService(BaseService):
    """
    Analytical service designed to calculate and track room occupancy statistics.
    Unlike persistent historical ledgers, this service strictly isolates data to 
    the current day, automatically resetting all accumulated counters at midnight (UTC).
    """

    def __init__(self):
        """
        Initializes the service and registers its nominal identifier for the 
        Digital Twin orchestration layer.
        """
        super().__init__()
        self.name = "RoomStatisticsService"

    def execute(self, data: Dict, dr_type: str = "room", attribute: str = None) -> Any:
        """
        Executes the statistical aggregation algorithm for room occupancy.
        
        Args:
            data (Dict): The payload containing dependency references and telemetry data.
                         Requires 'db_service', 'room_id', 'duration_minutes', and 'entries_to_add'.
            dr_type (str, optional): The target replica classification. Defaults to "room".
            attribute (str, optional): Unused targeted property parameter.
            
        Returns:
            Any: A single-element list containing the updated statistical record for today.
            
        Raises:
            ValueError: If critical identifiers or database services are missing from the payload,
                        or if the requested room replica does not exist.
        """
        db_service = data.get("db_service")
        room_id = data.get("room_id")
        duration_minutes = float(data.get("duration_minutes", 0.0))
        entries_to_add = int(data.get("entries_to_add", 1))

        # Validate mandatory structural dependencies
        if not db_service or not room_id:
            raise ValueError("db_service and room_id are strictly required to update statistics.")

        room_dr = db_service.get_dr(dr_type=dr_type, dr_id=room_id)
        if not room_dr:
            raise ValueError(f"Room with ID {room_id} not found.")

        # 1. Normalize the current timestamp to midnight UTC to ensure consistent daily bucketing
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        
        room_data = room_dr.get("data", {})
        occupancy_stats = room_data.get("occupancy_stats", [])

        current_daily_stat = None

        # 2. Evaluate chronological continuity: check if a statistical record already exists for the CURRENT day
        if occupancy_stats:
            # We assume the array holds at most one relevant record (today's data)
            last_stat = occupancy_stats[0]
            stat_date = last_stat.get("date")
            
            is_today = False
            # Type-safe date evaluation: handles naive/aware datetime objects or ISO strings
            if isinstance(stat_date, datetime) and stat_date.date() == today.date():
                is_today = True
            elif isinstance(stat_date, str) and stat_date.startswith(today.strftime("%Y-%m-%d")):
                is_today = True

            if is_today:
                current_daily_stat = last_stat

        # 3. Application Logic: Reset or Increment
        if current_daily_stat:
            # Same day: increment the existing accumulators
            current_daily_stat["pet_entries_count"] += entries_to_add
            current_daily_stat["daily_stay_duration_mins"] += duration_minutes
            new_stats_list = [current_daily_stat]
        else:
            # New day or initial execution: reset by provisioning a new, exclusive bucket for today
            new_stats_list = [{
                "date": today,
                "daily_stay_duration_mins": duration_minutes,
                "pet_entries_count": entries_to_add
            }]

        # 4. Database Synchronization: Persist the mutated ledger back to the target Digital Replica by overwriting the array
        update_payload = {
            "data.occupancy_stats": new_stats_list
        }

        db_service.update_dr(dr_type=dr_type, dr_id=room_id, update_data=update_payload)

        return new_stats_list