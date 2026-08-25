"""
Computer Vision Orchestration Service
=====================================
This module defines the service responsible for coordinating the YOLO-based 
object detection inference with the Digital Twin's state management. 
It orchestrates spatial transitions, handles room occupancy tracking, 
calculates stay durations, and enforces security policies via MQTT alarms 
and Telegram notifications.
"""

from src.services.base import BaseService
# Import the room statistics service to invoke it dynamically when a transition occurs
from src.services.room_statistics_service import RoomStatisticsService
from bson import ObjectId
import os
from flask import current_app
from datetime import datetime, timezone, timedelta
from src.application.bot.notifier import send_unauthorized_room_alert

class PetDetectionService(BaseService):
    """
    Service for executing pet detection via the YOLO machine learning model 
    and updating both the Digital Twin state and occupancy statistics.
    """

    def __init__(self):
        """
        Initializes the service and registers its nominal identifier.
        """
        super().__init__()
        self.name = "PetDetectionService"

    def execute(self, data: dict, **kwargs):
        """
        Executes the detection workflow and mutates the digital replicas accordingly.
        
        Args:
            data (dict): Standard payload containing the registered digital replicas.
            **kwargs: Must contain 'image_path', 'room_name', 'room_id', 'db_service', and 'pet_detector'.
            
        Returns:
            bool: True if a pet was detected, False otherwise.
            
        Raises:
            ValueError: If any required injection parameters are missing.
        """
        image_path = kwargs.get("image_path")
        room_name = kwargs.get("room_name")  
        room_id = kwargs.get("room_id")      # 1. NEW: Explicitly require the unique room identifier
        db_service = kwargs.get("db_service")
        pet_detector = kwargs.get("pet_detector")

        # Validate mandatory structural dependencies
        if not all([image_path, room_name, room_id, db_service, pet_detector]):
            raise ValueError("Missing required parameters for PetDetectionService.")

        # Extract the specific pet replica from the twin's environment
        replicas = data.get("digital_replicas", [])
        pet_ref = next((r for r in replicas if r.get("type") == "pet"), None)
        
        if not pet_ref:
            print("[PetDetectionService] No pet associated with this Digital Twin.")
            return False

        # Safely cast the identifier to a MongoDB ObjectId
        raw_pet_id = pet_ref.get("id") or pet_ref.get("_id")
        pet_id = ObjectId(raw_pet_id) if ObjectId.is_valid(raw_pet_id) else raw_pet_id
        
        # Retrieve current pet state from the database
        pet_db_data = db_service.get_dr("pet", pet_id)
        if not pet_db_data:
            return False

        previous_room = pet_db_data.get("data", {}).get("current_room", "")
        
        # Execute generic AI inference
        print(f"[PetDetectionService] Initiating YOLO inference on image: {image_path} to search for a generic pet")
        is_found = pet_detector.detect_any_pet(image_path)

        # --- IMAGE CLEANUP ---
        # Ensure temporary telemetry files are purged to prevent storage exhaustion
        try:
            if os.path.exists(image_path):
                os.remove(image_path)
                print(f"[PetDetectionService] DEBUG: Image {image_path} successfully removed from disk.")
        except Exception as e:
            print(f"[PetDetectionService] WARNING: Unable to delete image {image_path}: {e}")
        
        # =====================================================================
        # LOGIC 1: NO DETECTION
        # =====================================================================
        if not is_found:
            print("[PetDetectionService] NEGATIVE: No pet detected.")
            
            # We do absolutely nothing.
            # The room maintains its "occupied" status, the timer continues running,
            # and the pet retains its last known position.
            # The exit (and subsequent statistics calculation) will only occur in LOGIC 2,
            # when the pet is positively detected in a NEW room.
                
            return False

        # =====================================================================
        # LOGIC 2: PET DETECTED
        # =====================================================================
        print(f"[PetDetectionService] POSITIVE: Pet identified in '{room_name}'!")
        
        # Evaluate spatial transition: Check if the pet has moved to a NEW room
        if previous_room != room_name:
            
            # STEP 1: Process exit from the previous room (calculating accrued statistics)
            if previous_room:
                # Isolate the search strictly within the current Digital Twin to prevent cross-home collisions
                previous_room_id = self._find_room_id_in_twin(previous_room, replicas, db_service)
                if previous_room_id:
                    self._handle_pet_exit(previous_room_id, db_service)
                
            # STEP 2: Process entry into the new room using the unique ID
            self._handle_pet_entry(room_id, db_service)
            
            # STEP 3: Update the current location property on the pet's Digital Replica
            # We preserve the room_name for frontend readability, while backend logic relies on IDs
            db_service.update_dr("pet", pet_id, {"data.current_room": room_name})
            print(f"  -> DB Pet: 'current_room' successfully updated to '{room_name}'.")
            
            # STEP 4: Evaluate security policies and trigger MQTT/Telegram alarms if necessary
            self._trigger_alarms(room_id, db_service, str(pet_id))
            
        return True

    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------

    def _find_room_id_in_twin(self, room_name: str, replicas: list, db_service) -> str:
        """
        Locates the exact room ID within the current Digital Twin context.
        This prevents cross-environment collisions when exiting a room by ensuring 
        we don't query a room with the same name belonging to another user.
        """
        for rep in replicas:
            if rep.get("type") == "room":
                raw_id = rep.get("id") or rep.get("_id")
                search_id = ObjectId(raw_id) if ObjectId.is_valid(raw_id) else raw_id
                room_dr = db_service.get_dr("room", search_id)
                if room_dr and room_dr.get("profile", {}).get("name") == room_name:
                    return str(raw_id)
        return None

    def _handle_pet_exit(self, room_id: str, db_service):
        """
        Manages the logic for exiting a room: calculates elapsed time and updates aggregated statistics.
        Refactored to rely exclusively on unique entity IDs.
        """
        search_id = ObjectId(room_id) if ObjectId.is_valid(room_id) else room_id
        room_data = db_service.get_dr("room", search_id)
        if not room_data:
            return
            
        room_name = room_data.get("profile", {}).get("name", "Unknown")
        current_status = room_data.get("data", {}).get("status", "empty")

        if current_status == "occupied":
            last_entry_time = room_data.get("data", {}).get("last_entry_time")
            duration_minutes = 0.0

            # Calculate the elapsed minutes since the initial entry
            if last_entry_time:
                # 1. If it arrives as an ISO string, parse it and inject the UTC timezone
                if isinstance(last_entry_time, str):
                    last_entry_time = datetime.fromisoformat(last_entry_time.replace("Z", "+00:00"))
                # 2. If it arrives as a naive datetime from MongoDB, force the UTC timezone
                elif isinstance(last_entry_time, datetime) and last_entry_time.tzinfo is None:
                    last_entry_time = last_entry_time.replace(tzinfo=timezone.utc)

                now = datetime.now(timezone.utc)
                
                # 3. Truncate at midnight if the entry spans across days
                if last_entry_time.date() < now.date():
                    start_time_for_calc = now.replace(hour=0, minute=0, second=0, microsecond=0)
                else:
                    start_time_for_calc = last_entry_time

                # Compute the final temporal difference
                time_diff = now - start_time_for_calc
                duration_minutes = time_diff.total_seconds() / 60.0

            # 1. Invoke the statistics service to append the calculated stay duration
            stats_service = RoomStatisticsService()
            stats_service.execute({
                "db_service": db_service,
                "room_id": str(room_id),
                "duration_minutes": duration_minutes,
                "entries_to_add": 1
            })

            # 2. Reset the room's physical state and clear the active timer
            db_service.update_dr("room", search_id, {
                "data.status": "empty",
                "data.last_entry_time": None
            })
            print(f"  -> DB Room ID '{room_id}' ({room_name}) cleared. Statistics updated ({duration_minutes:.2f} min).")


    def _handle_pet_entry(self, room_id: str, db_service):
        """
        Manages the logic for entering a room: mutates state to 'occupied' and starts the timer.
        Refactored to rely exclusively on unique entity IDs.
        """
        search_id = ObjectId(room_id) if ObjectId.is_valid(room_id) else room_id
        room_data = db_service.get_dr("room", search_id)
        if not room_data:
            print(f"  -> WARNING: The room with ID '{room_id}' does not exist in the database.")
            return

        db_service.update_dr("room", search_id, {
            "data.status": "occupied",
            "data.last_entry_time": datetime.now(timezone.utc)
        })
        print(f"  -> DB Room ID '{room_id}' occupied. Timer initiated.")


    def _trigger_alarms(self, room_id: str, db_service, pet_id: str):
        """
        Evaluates room permission levels and dispatches MQTT hardware alarms 
        and Telegram software notifications if policies are violated.
        Refactored to rely exclusively on unique entity IDs.
        """
        search_room_id = ObjectId(room_id) if ObjectId.is_valid(room_id) else room_id
        room_data = db_service.get_dr("room", search_room_id)
        if not room_data:
            return
            
        permission_level = room_data.get("profile", {}).get("permission_level", "allowed")
        room_name = room_data.get("profile", {}).get("name", "Unknown")
        
        search_pet_id = ObjectId(pet_id) if ObjectId.is_valid(pet_id) else pet_id
        pet_dr = db_service.get_dr("pet", search_pet_id)
        if not pet_dr:
            return
        last_buzzer_start = pet_dr.get("data", {}).get("last_buzzer_start_time")
        
        # Policy Enforcement: Activate Alarm (ON)
        if permission_level == "forbidden":
            if not last_buzzer_start:
                db_service.update_dr("pet", search_pet_id, {
                    "data.last_buzzer_start_time": datetime.now(timezone.utc),
                    "data.buzzer_state": "ON"
                })
            else:
                db_service.update_dr("pet", search_pet_id, {
                    "data.buzzer_state": "ON"
                })
                
            # 1. Hardware activation via MQTT Broker
            if hasattr(current_app, 'mqtt_manager'):
                try:
                    current_app.mqtt_manager.client.publish("home/sound", "ON", qos=1)
                    print(f"  -> 🚨 ALARM: Pet detected in a forbidden zone ({room_name})! Buzzer activated.")
                except Exception as e:
                    print(f"  -> [MQTT] Error: {e}")

            # 2. Software notification dispatch via Telegram
            try:
                send_unauthorized_room_alert(room_name)
                current_time = datetime.now().strftime("%H:%M:%S")
                print(f"  -> 📲 TELEGRAM: [{current_time}] Intrusion notification dispatched for room {room_name}.")
            except Exception as e:
                print(f"  -> [TELEGRAM] Notification dispatch error: {e}")

        # Policy Enforcement: Deactivate Alarm (OFF)
        elif permission_level == "allowed":
            if last_buzzer_start:
                duration_minutes = 0.0
                
                if isinstance(last_buzzer_start, str):
                    last_buzzer_start = datetime.fromisoformat(last_buzzer_start.replace("Z", "+00:00"))
                elif isinstance(last_buzzer_start, datetime) and last_buzzer_start.tzinfo is None:
                    last_buzzer_start = last_buzzer_start.replace(tzinfo=timezone.utc)
                    
                time_diff = datetime.now(timezone.utc) - last_buzzer_start
                duration_minutes = time_diff.total_seconds() / 60.0
                
                # Invoke the PetStatisticsService to record the violation duration
                from src.services.pet_statistics_service import PetStatisticsService
                stats_service = PetStatisticsService()
                stats_service.execute({
                    "db_service": db_service,
                    "pet_id": str(pet_id),
                    "duration_minutes": duration_minutes,
                    "violations_to_add": 1
                })
                
                db_service.update_dr("pet", search_pet_id, {
                    "data.last_buzzer_start_time": None,
                    "data.buzzer_state": "OFF"
                })
            
            if hasattr(current_app, 'mqtt_manager'):
                try:
                    # Instruct hardware to silence the buzzer
                    current_app.mqtt_manager.client.publish("home/sound", "OFF", qos=1)
                    print(f"  -> ✅ Safe zone confirmed ({room_name}). Buzzer deactivated.")
                except Exception as e:
                    print(f"  -> [MQTT] Error: {e}")