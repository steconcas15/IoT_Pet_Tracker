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

    def _calculate_learning_trends(self, stats: list) -> Dict[str, Any]:
        """
        Analyzes the 30-day historical ledger to calculate learning trends.
        Compares recent behavioral data against a preceding temporal window 
        to determine training progress.
        
        Args:
            stats (list): The chronological array of daily statistical buckets.
            
        Returns:
            Dict[str, Any]: A dictionary containing calculated performance metrics 
                            and a qualitative learning status.
        """
        # 1. Initialize the default analytics payload
        analytics = {
            "reaction_time_trend_percent": 0.0,
            "violations_trend_percent": 0.0,
            "learning_status": "Insufficient Data",
            "avg_reaction_time_recent": 0.0
        }

        # 2. Require a minimum temporal baseline to perform comparative analysis
        if len(stats) < 2:
            return analytics

        # 3. Partition the ledger into two comparative windows (max 7 days each)
        mid_point = min(7, len(stats) // 2) if len(stats) < 14 else 7
        
        recent_stats = stats[:mid_point]
        previous_stats = stats[mid_point:mid_point*2]

        if not previous_stats:
            return analytics

        # Helper function to aggregate raw metrics safely
        def get_totals(data_slice):
            tot_duration = sum(d.get("auto_duration_mins", 0.0) for d in data_slice)
            tot_violations = sum(d.get("auto_violations_count", 0) for d in data_slice)
            avg_reaction = (tot_duration / tot_violations) if tot_violations > 0 else 0.0
            return tot_violations, avg_reaction

        # 4. Extract aggregated totals and averages for both temporal windows
        recent_violations, recent_reaction = get_totals(recent_stats)
        prev_violations, prev_reaction = get_totals(previous_stats)

        analytics["avg_reaction_time_recent"] = round(recent_reaction, 2)

        # 5. Calculate percentage variations using the mathematical formula:
        # \( \frac{\text{Recent} - \text{Previous}}{\text{Previous}} \times 100 \)
        if prev_reaction > 0:
            analytics["reaction_time_trend_percent"] = round(((recent_reaction - prev_reaction) / prev_reaction) * 100, 2)
        
        if prev_violations > 0:
            analytics["violations_trend_percent"] = round(((recent_violations - prev_violations) / prev_violations) * 100, 2)

        # 6. Evaluate the calculated trends to assign a qualitative learning state
        if analytics["reaction_time_trend_percent"] < -10 or analytics["violations_trend_percent"] < -10:
            analytics["learning_status"] = "Learning (Improving)"
        elif recent_violations == 0 and prev_violations == 0:
            analytics["learning_status"] = "Trained (No Violations)"
        elif analytics["reaction_time_trend_percent"] > 10 or analytics["violations_trend_percent"] > 10:
            analytics["learning_status"] = "Regressing / Disobedient"
        else:
            analytics["learning_status"] = "Stationary"

        return analytics

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

        # 5. Behavioral Analytics: Extract learning trends from the updated historical ledger
        learning_analytics = self._calculate_learning_trends(daily_buzzer_stats)

        # 6. Database Synchronization: Persist the mutated ledger and analytics back to the target Digital Replica
        update_payload = {
            "data.daily_buzzer_stats": daily_buzzer_stats,
            "data.learning_analytics": learning_analytics
        }
        db_service.update_dr(dr_type=dr_type, dr_id=pet_id, update_data=update_payload) 

        return daily_buzzer_stats