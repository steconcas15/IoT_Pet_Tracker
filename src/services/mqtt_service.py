import paho.mqtt.client as mqtt
import ssl
import threading

class MQTTManager:
    """
    Servizio dedicato alla gestione della connessione MQTT e delle callback associate.
    Gestisce in tempo reale lo stato LWT delle porte (sensori ultrasuoni) e delle stanze (telecamere).
    """
    def __init__(self, app):
        self.app = app
        self.client = mqtt.Client(userdata={'app': self.app})
        self.offline_timer = None
        self.online_timer = None  # Nuovo timer per il ritorno alla normalità
        
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print("[MQTT] Connesso al broker HiveMQ con successo!")
            client.subscribe("casa/+/stato")
        else:
            print(f"[MQTT] Errore di connessione. Codice: {rc}")

    def _perform_offline_check(self, app):
        """Eseguita 30 secondi dopo il primo segnale OFFLINE per calcolare i danni"""
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

                    total_devices = 0
                    offline_devices = []

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
                            total_devices += 1
                            name = dr.get("profile", {}).get("name", "Sconosciuto")

                            status = "ONLINE"
                            if dr_type == "room":
                                status = dr.get("data", {}).get("camera_status", "ONLINE")
                            elif dr_type == "door":
                                status = dr.get("data", {}).get("sensor_status", "ONLINE")
                            elif dr_type == "pet":
                                status = dr.get("data", {}).get("buzzer_status", "ONLINE")

                            if status and str(status).strip().upper() == "OFFLINE":
                                offline_devices.append(name)

                    if len(offline_devices) > 0:
                        from bot.notifier import send_offline_alert
                        all_offline = (len(offline_devices) == total_devices and total_devices > 0)
                        send_offline_alert(home_id, offline_devices, all_offline)
                        
        except Exception as e:
            print(f"[MQTT TIMER FATAL ERROR] Eccezione critica nel thread OFFLINE: {str(e)}")

    def _perform_online_check(self, app):
        """Eseguita 10 secondi dopo che un dispositivo torna ONLINE, controlla se tutto è ok."""
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
                            status = "ONLINE"
                            if dr_type == "room":
                                status = dr.get("data", {}).get("camera_status", "ONLINE")
                            elif dr_type == "door":
                                status = dr.get("data", {}).get("sensor_status", "ONLINE")
                            elif dr_type == "pet":
                                status = dr.get("data", {}).get("buzzer_status", "ONLINE")

                            if status and str(status).strip().upper() == "OFFLINE":
                                offline_count += 1

                    # Se 0 dispositivi sono offline in questa casa, avviamo il recovery
                    if offline_count == 0:
                        from bot.notifier import send_online_recovery
                        send_online_recovery(home_id)
                        
        except Exception as e:
            print(f"[MQTT TIMER FATAL ERROR] Eccezione critica nel thread ONLINE: {str(e)}")


    def _on_message(self, client, userdata, msg):
            app = userdata['app']
            topic = msg.topic
            
            payload = msg.payload.decode('utf-8').strip() 
            parts = topic.split('/')
            
            if len(parts) >= 3:
                device_name = parts[1]
                topic_type = parts[2]
                with app.app_context():
                    db_service = app.config['DB_SERVICE']
                    
                    if topic_type == "stato":
                        if device_name == "buzzer":
                            try:
                                pets = db_service.query_drs("pet", {})
                                for pet in pets:
                                    db_service.update_dr(
                                        dr_type="pet", 
                                        dr_id=pet["_id"], 
                                        update_data={"data.buzzer_status": payload}
                                    )
                            except Exception as e:
                                pass
                        else:
                            try:
                                query = {"profile.name": device_name}
                                doors = db_service.query_drs("door", query)
                                for door in doors:
                                    db_service.update_dr(dr_type="door", dr_id=door["_id"], update_data={"data.sensor_status": payload})
                                
                                rooms = db_service.query_drs("room", query)
                                for room in rooms:
                                    db_service.update_dr(dr_type="room", dr_id=room["_id"], update_data={"data.camera_status": payload})
                            except Exception as e:
                                pass

                        # GESTIONE NOTIFICHE OFFLINE 
                        if payload.upper() == "OFFLINE":
                            if self.offline_timer is None or not self.offline_timer.is_alive():
                                print("[MQTT] Dispositivo andato OFFLINE. Avvio il timer di 30 secondi...")
                                self.offline_timer = threading.Timer(30.0, self._perform_offline_check, args=[app])
                                self.offline_timer.start()

                        # GESTIONE RITORNO ALLA NORMALITA' (ONLINE)
                        elif payload.upper() == "ONLINE":
                            if self.online_timer is None or not self.online_timer.is_alive():
                                print("[MQTT] Dispositivo tornato ONLINE. Verifico la situazione della casa...")
                                # Timer più rapido (10 secondi), aspetta solo che tutti i dispositivi abbiano 
                                # finito di inviare il segnale LWT se si riaccende tutto assieme
                                self.online_timer = threading.Timer(10.0, self._perform_online_check, args=[app])
                                self.online_timer.start()

    def start(self, broker, port, username, password):
        try:
            self.client.username_pw_set(username, password)
            self.client.tls_set(cert_reqs=ssl.CERT_NONE)
            self.client.tls_insecure_set(True)
            self.client.connect(broker, port, 60)
            self.client.loop_start()
        except Exception as e:
            print(f"[MQTT] Impossibile avviare il client: {str(e)}")

    def stop(self):
        # Aggiunta chiusura per entrambi i timer 
        if self.offline_timer and self.offline_timer.is_alive():
            self.offline_timer.cancel()
        if self.online_timer and self.online_timer.is_alive():
            self.online_timer.cancel()
            
        self.client.loop_stop()
        self.client.disconnect()