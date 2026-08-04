import paho.mqtt.client as mqtt
import ssl

class MQTTManager:
    """
    Servizio dedicato alla gestione della connessione MQTT e delle callback associate.
    Gestisce in tempo reale lo stato LWT delle porte (sensori ultrasuoni) e delle stanze (telecamere).
    """
    def __init__(self, app):
        self.app = app
        self.client = mqtt.Client(userdata={'app': self.app})
        
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print("[MQTT] Connesso al broker HiveMQ con successo!")
            # Iscrizione a un unico topic wildcard per buzzer, porte e telecamere
            client.subscribe("casa/+/stato")
        else:
            print(f"[MQTT] Errore di connessione. Codice: {rc}")

    def _on_message(self, client, userdata, msg):
            app = userdata['app']
            topic = msg.topic
            payload = msg.payload.decode('utf-8')
            parts = topic.split('/')
            
            if len(parts) >= 3:
                device_name = parts[1]
                topic_type = parts[2]
                with app.app_context():
                    db_service = app.config['DB_SERVICE']
                    
                    # ==========================================
                    # GESTIONE STATO UNIFICATO (PORTE, BUZZER, CAMERE)
                    # ==========================================
                    if topic_type == "stato":
                        
                        # 1. Caso specifico: Buzzer (casa/buzzer/stato)
                        if device_name == "buzzer":
                            try:
                                pets = db_service.query_drs("pet", {})
                                for pet in pets:
                                    db_service.update_dr(
                                        dr_type="pet", 
                                        dr_id=pet["_id"], 
                                        update_data={"data.buzzer_status": payload}
                                    )
                                    print(f"[MQTT] Stato del buzzer aggiornato a: {payload}")
                            except Exception as e:
                                print(f"[MQTT] Errore durante l'aggiornamento del buzzer: {str(e)}")
                                
                        # 2. Caso generico: Sensori Porte e Telecamere Stanze
                        else:
                            try:
                                query = {"profile.name": device_name}
                                
                                # Cerca e aggiorna se è una porta
                                doors = db_service.query_drs("door", query)
                                for door in doors:
                                    db_service.update_dr(
                                        dr_type="door", 
                                        dr_id=door["_id"], 
                                        update_data={"data.sensor_status": payload}
                                    )
                                    print(f"[MQTT] Stato della porta '{device_name}' aggiornato a: {payload}")
                                
                                # Cerca e aggiorna se è una stanza (telecamera)
                                rooms = db_service.query_drs("room", query)
                                for room in rooms:
                                    db_service.update_dr(
                                        dr_type="room", 
                                        dr_id=room["_id"], 
                                        update_data={"data.camera_status": payload}
                                    )
                                    print(f"[MQTT] Stato telecamera '{device_name}' aggiornato a: {payload}")
                                    
                            except Exception as e:
                                print(f"[MQTT] Errore aggiornamento per '{device_name}': {str(e)}")

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
        self.client.loop_stop()
        self.client.disconnect()