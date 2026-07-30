import paho.mqtt.client as mqtt
import ssl

class MQTTManager:
    """
    Servizio dedicato alla gestione della connessione MQTT e delle callback associate.
    Gestisce in tempo reale lo stato LWT delle porte (sensori ultrasuoni) e delle stanze (telecamere).
    """
    def __init__(self, app):
        self.app = app
        # Passiamo l'app Flask nel parametro userdata per accedere al DB nei thread asincroni
        self.client = mqtt.Client(userdata={'app': self.app})
        
        # Associazione delle callback
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print("[MQTT] Connesso al broker HiveMQ con successo!")
            # Iscrizione ai topic wildcard per i sensori delle porte
            client.subscribe("casa/+/stato")
            # Iscrizione ai topic wildcard per lo stato delle telecamere nelle stanze
            client.subscribe("casa/+/camera_stato")
        else:
            print(f"[MQTT] Errore di connessione. Codice: {rc}")

    def _on_message(self, client, userdata, msg):
        app = userdata['app']
        topic = msg.topic
        payload = msg.payload.decode('utf-8')
        
        # Estrazione delle parti dal topic
        # Esempio Porta: "casa/porta_u1/stato" -> parts[0]="casa", parts[1]="porta_u1", parts[2]="stato"
        # Esempio Camera: "casa/salotto/camera_stato" -> parts[0]="casa", parts[1]="salotto", parts[2]="camera_stato"
        parts = topic.split('/')
        
        if len(parts) >= 3:
            device_name = parts[1]
            topic_type = parts[2]
            
            # Necessario per usare i componenti Flask in un thread separato
            with app.app_context():
                db_service = app.config['DB_SERVICE']
                
                # ==========================================
                # 1. GESTIONE SENSORI PORTE
                # ==========================================
                if topic_type == "stato":
                    try:
                        query = {"profile.name": device_name}
                        doors = db_service.query_drs("door", query)
                        
                        for door in doors:
                            door_id = door["_id"]
                            db_service.update_dr(
                                dr_type="door", 
                                dr_id=door_id, 
                                update_data={"data.sensor_status": payload}
                            )
                            print(f"[MQTT] Stato della porta '{device_name}' aggiornato a: {payload}")
                    except Exception as e:
                        print(f"[MQTT] Errore durante l'aggiornamento della porta '{device_name}': {str(e)}")

                # ==========================================
                # 2. GESTIONE TELECAMERE STANZE
                # ==========================================
                elif topic_type == "camera_stato":
                    try:
                        query = {"profile.name": device_name}
                        rooms = db_service.query_drs("room", query)
                        
                        for room in rooms:
                            room_id = room["_id"]
                            db_service.update_dr(
                                dr_type="room", 
                                dr_id=room_id, 
                                update_data={"data.camera_status": payload}
                            )
                            print(f"[MQTT] Stato telecamera della stanza '{device_name}' aggiornato a: {payload}")
                    except Exception as e:
                        print(f"[MQTT] Errore durante l'aggiornamento della telecamera '{device_name}': {str(e)}")

    def start(self, broker, port, username, password):
        """Connette il client al broker sicuro e avvia il loop in background."""
        try:
            # 1. Imposta Utente e Password
            self.client.username_pw_set(username, password)
            
            # 2. Configura il contesto TLS
            self.client.tls_set(cert_reqs=ssl.CERT_NONE)
            self.client.tls_insecure_set(True)
            
            # 3. Connessione e avvio
            self.client.connect(broker, port, 60)
            self.client.loop_start()
        except Exception as e:
            print(f"[MQTT] Impossibile avviare il client: {str(e)}")

    def stop(self):
        """Ferma il loop e disconnette il client in modo pulito."""
        self.client.loop_stop()
        self.client.disconnect()