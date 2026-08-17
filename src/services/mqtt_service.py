"""
MQTT Connection & Telemetry Management Module
=============================================
This module provides a dedicated service for managing the MQTT client lifecycle, 
asynchronous callbacks, and real-time state synchronization. It is primarily 
responsible for handling Last Will and Testament (LWT) statuses for IoT devices, 
such as ultrasonic door sensors and room cameras, ensuring the Digital Twin 
accurately reflects the physical environment's connectivity state.
"""

import paho.mqtt.client as mqtt
import ssl
import threading

class MQTTManager:
    """
    Service dedicated to orchestrating the MQTT connection and associated callbacks.
    Handles real-time Last Will and Testament (LWT) states for doors (ultrasonic sensors) 
    and rooms (cameras), triggering delayed health-check protocols when devices drop offline.
    """
    def __init__(self, app):
        """
        Initializes the MQTT Manager with the Flask application context.
        Sets up threading timers to prevent notification spam during brief network fluctuations.
        """
        self.app = app
        self.client = mqtt.Client(userdata={'app': self.app})
        
        # Timers used to debounce network state changes
        self.offline_timer = None
        self.online_timer = None  # Timer for verifying complete system recovery
        
        # Bind asynchronous event callbacks
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, rc):
        """
        Callback executed upon successful connection to the MQTT broker.
        Subscribes to global state topics and performs necessary cloud state cleanup.
        """
        if rc == 0:
            print("[MQTT] Successfully connected to HiveMQ broker!")
            # Subscribe to all state topics using the single-level wildcard '+'
            client.subscribe("home/+/state")
            
            # --- BEGIN CLOUD CLEANUP ---
            # Injecting the exact ID of the door (ultrasonic sensor) for state reset
            door_id = "7d0b2bd9-8320-4337-a0c0-f8aedc9f118c"
            
            # Publish a "RESET" empty payload with retain=True and qos=1 to overwrite ghost states
            client.publish(f"home/{door_id}", "", retain=True, qos=1)
            print(f"[MQTT] Cloud memory successfully cleared for door {door_id}")
            # --- END CLOUD CLEANUP ---
            
        else:
            print(f"[MQTT] Connection error. Return code: {rc}")

    def _perform_offline_check(self, app):
        """
        Health-check routine executed 30 seconds after the initial OFFLINE signal.
        Aggregates the current state of all devices across all homes to assess total network damage
        and dispatches grouped alerts via Telegram.
        """
        try:
            with app.app_context():
                db_service = app.config['DB_SERVICE']
                dt_factory = app.config['DT_FACTORY']
                
                # Retrieve all users to map out unique owned homes
                users = db_service.query_drs("user", {})
                unique_homes = set()
                for u in users:
                    for h in u.get("data", {}).get("owned_homes", []):
                        unique_homes.add(h)

                # Iterate through all homes to calculate offline statistics
                for home_id in unique_homes:
                    dt_data = dt_factory.get_dt(home_id)
                    if not dt_data: continue

                    total_devices = 0
                    offline_devices = []

                    # Check the real-time status of every registered replica
                    for replica in dt_data.get("digital_replicas", []):
                        dr_type = replica.get("type")
                        raw_id = replica.get("id")
                        # Defensive cast to ensure string comparison
                        dr_id = str(raw_id) if not isinstance(raw_id, str) else raw_id
                        
                        try:
                            dr = db_service.get_dr(dr_type, dr_id)
                        except Exception:
                            continue
                            
                        if not dr: continue

                        # Evaluate network-capable entities
                        if dr_type in ["room", "door", "pet"]:
                            total_devices += 1
                            name = dr.get("profile", {}).get("name", "Unknown")

                            status = "ONLINE"
                            if dr_type == "room":
                                status = dr.get("data", {}).get("camera_status", "ONLINE")
                            elif dr_type == "door":
                                status = dr.get("data", {}).get("sensor_status", "ONLINE")
                            elif dr_type == "pet":
                                status = dr.get("data", {}).get("buzzer_status", "ONLINE")

                            # Flag device if the database records an active OFFLINE state
                            if status and str(status).strip().upper() == "OFFLINE":
                                offline_devices.append(name)

                    # Dispatch alert if any devices remain offline after the 30-second window
                    if len(offline_devices) > 0:
                        from bot.notifier import send_offline_alert
                        all_offline = (len(offline_devices) == total_devices and total_devices > 0)
                        send_offline_alert(home_id, offline_devices, all_offline)
                        
        except Exception as e:
            print(f"[MQTT TIMER FATAL ERROR] Critical exception in OFFLINE thread: {str(e)}")

    def _perform_online_check(self, app):
        """
        Recovery routine executed 10 seconds after a device returns ONLINE.
        Verifies if the entire environment has stabilized (0 offline devices) and notifies the user.
        """
        try:
            with app.app_context():
                db_service = app.config['DB_SERVICE']
                dt_factory = app.config['DT_FACTORY']
                
                users = db_service.query_drs("user", {})
                unique_homes = set()
                for u in users:
                    for h in u.get("data", {}).get("owned_homes", []):
                        unique_homes.add(h)

                for home_id in unique_homes:
                    dt_data = dt_factory.get_dt(home_id)
                    if not dt_data: continue

                    offline_count = 0
                    online_devices = [] # Debug tracking array

                    for replica in dt_data.get("digital_replicas", []):
                        dr_type = replica.get("type")
                        raw_id = replica.get("id")
                        dr_id = str(raw_id) if not isinstance(raw_id, str) else raw_id
                        
                        try:
                            dr = db_service.get_dr(dr_type, dr_id)
                        except Exception:
                            continue
                            
                        if not dr: continue

                        if dr_type in ["room", "door", "pet"]:
                            name = dr.get("profile", {}).get("name", dr_id)
                            
                            status = "ONLINE"
                            if dr_type == "room":
                                status = dr.get("data", {}).get("camera_status", "ONLINE")
                            elif dr_type == "door":
                                status = dr.get("data", {}).get("sensor_status", "ONLINE")
                            elif dr_type == "pet":
                                status = dr.get("data", {}).get("buzzer_status", "ONLINE")

                            if status and str(status).strip().upper() == "OFFLINE":
                                offline_count += 1
                            else:
                                online_devices.append(name) # Track recovered devices

                    # --- DEBUG CONSOLE OUTPUT ---
                    print(f"[MQTT DEBUG] Home {home_id}: ONLINE Devices -> {online_devices}")
                    if offline_count > 0:
                        print(f"[MQTT DEBUG] Home {home_id}: There are still {offline_count} OFFLINE devices.")

                    # Trigger recovery notification if the environment is fully operational
                    if offline_count == 0:
                        print(f"[MQTT DEBUG] Home {home_id}: All devices are ONLINE! Sending recovery notification.")
                        from bot.notifier import send_online_recovery
                        send_online_recovery(home_id)
                        
        except Exception as e:
            print(f"[MQTT TIMER FATAL ERROR] Critical exception in ONLINE thread: {str(e)}")

    def _on_message(self, client, userdata, msg):
        """
        Asynchronous callback triggered upon receiving an MQTT message.
        Parses device states and triggers the appropriate debouncing timers.
        """
        app = userdata['app']
        topic = msg.topic
        
        payload = msg.payload.decode('utf-8').strip() 
        parts = topic.split('/')
        
        if len(parts) >= 3:
            device_id = parts[1]  # Extracted unique device identifier
            topic_type = parts[2]
            
            with app.app_context():
                db_service = app.config['DB_SERVICE']
                
                if topic_type == "state":
                    # Since device type (room, door, pet) is abstracted at the MQTT layer,
                    # sequentially attempt to resolve the identifier against the database.
                    try:
                        if db_service.get_dr("room", device_id):
                            db_service.update_dr(dr_type="room", dr_id=device_id, update_data={"data.camera_status": payload})
                        elif db_service.get_dr("door", device_id):
                            db_service.update_dr(dr_type="door", dr_id=device_id, update_data={"data.sensor_status": payload})
                        elif db_service.get_dr("pet", device_id):
                            db_service.update_dr(dr_type="pet", dr_id=device_id, update_data={"data.buzzer_status": payload})
                    except Exception as e:
                        print(f"[MQTT] Error updating LWT state for ID {device_id}: {str(e)}")

                    # OFFLINE NOTIFICATION MANAGEMENT 
                    if payload.upper() == "OFFLINE":
                        if self.offline_timer is None or not self.offline_timer.is_alive():
                            print("[MQTT] Device went OFFLINE. Starting the 30-second debounce timer...")
                            self.offline_timer = threading.Timer(30.0, self._perform_offline_check, args=[app])
                            self.offline_timer.start()

                    # ONLINE RECOVERY MANAGEMENT
                    elif payload.upper() == "ONLINE":
                        if self.online_timer is None or not self.online_timer.is_alive():
                            print("[MQTT] Device returned ONLINE. Verifying home environment stability...")
                            self.online_timer = threading.Timer(10.0, self._perform_online_check, args=[app])
                            self.online_timer.start()

    def start(self, broker, port, username, password):
        """
        Configures TLS/SSL context and initializes the non-blocking MQTT network loop.
        """
        try:
            self.client.username_pw_set(username, password)
            self.client.tls_set(cert_reqs=ssl.CERT_NONE)
            self.client.tls_insecure_set(True)
            self.client.connect(broker, port, 60)
            self.client.loop_start()
        except Exception as e:
            print(f"[MQTT] Unable to start client: {str(e)}")

    def stop(self):
        """
        Gracefully terminates threaded timers and cleanly disconnects from the MQTT broker.
        """
        # Cancel any active asynchronous timers to prevent execution during shutdown
        if self.offline_timer and self.offline_timer.is_alive():
            self.offline_timer.cancel()
        if self.online_timer and self.online_timer.is_alive():
            self.online_timer.cancel()
            
        self.client.loop_stop()
        self.client.disconnect()