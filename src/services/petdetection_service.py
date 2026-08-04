from src.services.base import BaseService
from bson import ObjectId
import os
from flask import current_app

class PetDetectionService(BaseService):
    """
    Servizio per il rilevamento del pet tramite YOLO e l'aggiornamento
    dello stato del Digital Twin.
    """

    def __init__(self):
        super().__init__()
        self.name = "PetDetectionService"

    def execute(self, data: dict, **kwargs):
        """
        Esegue il rilevamento del pet e aggiorna le repliche digitali.
        """
        image_path = kwargs.get("image_path")
        room_name = kwargs.get("room_name")  
        db_service = kwargs.get("db_service")
        pet_detector = kwargs.get("pet_detector")

        if not all([image_path, room_name, db_service, pet_detector]):
            raise ValueError("Parametri mancanti per PetDetectionService.")

        replicas = data.get("digital_replicas", [])
        pet_ref = next((r for r in replicas if r.get("type") == "pet"), None)
        
        if not pet_ref:
            print("[PetDetectionService] Nessun pet associato a questo Digital Twin.")
            return False

        raw_pet_id = pet_ref.get("_id")
        
        pet_id = ObjectId(raw_pet_id) if ObjectId.is_valid(raw_pet_id) else raw_pet_id
        
        pet_db_data = db_service.get_dr("pet", pet_id)
        if not pet_db_data:
            return False

        # Rimosso il recupero del "target" specifico (es. dog/cat)
        previous_room = pet_db_data.get("data", {}).get("current_room", "")
        
        # Esecuzione modello IA generica
        print(f"[PetDetectionService] Avvio inferenza YOLO su immagine: {image_path} per cercare un pet generico")
        is_found = pet_detector.detect_any_pet(image_path)

        # --- RIMOZIONE IMMAGINE ---
        try:
            if os.path.exists(image_path):
                os.remove(image_path)
                print(f"[PetDetectionService] DEBUG: Immagine {image_path} eliminata dal disco con successo.")
        except Exception as e:
            print(f"[PetDetectionService] ATTENZIONE: Impossibile eliminare l'immagine {image_path}: {e}")
        
        # =====================================================================
        # LOGICA 1: NESSUN RILEVAMENTO
        # =====================================================================
        if not is_found:
            print("[PetDetectionService] NEGATIVO: Nessun pet rilevato.")
            return False

        # =====================================================================
        # LOGICA 2: PET RILEVATO
        # =====================================================================
        print(f"[PetDetectionService] POSITIVO: Pet identificato in '{room_name}'!")
        
        pet_metadata = pet_db_data.get("metadata", {})

        # STEP 1: Svuota la stanza precedente
        if previous_room and previous_room != room_name:
            old_rooms = db_service.query_drs("room", {"profile.name": previous_room})
            if old_rooms:
                old_room_data = old_rooms[0]
                old_room_id = old_room_data["_id"]
                old_room_metadata = old_room_data.get("metadata", {})
                try:
                    db_service.update_dr(
                        "room", 
                        old_room_id, 
                        {"data.status": "empty", "metadata": old_room_metadata}
                    )
                    print(f"  -> DB Stanza: '{previous_room}' liberata (status: empty).")
                except Exception as e:
                    print(f"  -> ERRORE DB Stanza '{previous_room}': {e}")
        
        # STEP 2: Aggiorna la posizione del pet sulla sua DR
        try:
            db_service.update_dr(
                "pet", 
                pet_id, 
                {"data.current_room": room_name, "metadata": pet_metadata}
            )
            print(f"  -> DB Pet: 'current_room' aggiornata a '{room_name}'.")
        except Exception as e:
            print(f"  -> ERRORE DB Pet: Impossibile aggiornare la posizione: {e}")
            
        # STEP 3: Occupa la nuova stanza e GESTIONE ALLARME
        new_rooms = db_service.query_drs("room", {"profile.name": room_name})
        if new_rooms:
            new_room_data = new_rooms[0]
            new_room_id = new_room_data["_id"]
            new_room_metadata = new_room_data.get("metadata", {})
            
            permission_level = new_room_data.get("profile", {}).get("permission_level", "allowed")
            
            try:
                db_service.update_dr(
                    "room", 
                    new_room_id, 
                    {"data.status": "occupied", "metadata": new_room_metadata}
                )
                print(f"  -> DB Stanza: '{room_name}' occupata (status: occupied).")
            except Exception as e:
                print(f"  -> ERRORE DB Stanza '{room_name}': {e}")
                
            # INVIO COMANDI MQTT
            if hasattr(current_app, 'mqtt_manager'):
                try:
                    mqtt_client = current_app.mqtt_manager.client
                    if permission_level == "forbidden":
                        print(f"  -> 🚨 ALLARME: Il pet è in una stanza vietata ({room_name})! Attivazione buzzer.")
                        mqtt_client.publish("casa/sound", "ON")
                    elif permission_level == "allowed":
                        print(f"  -> ✅ Stanza sicura ({room_name}). Disattivazione buzzer.")
                        mqtt_client.publish("casa/sound", "OFF")
                except Exception as e:
                    print(f"  -> [MQTT] Errore durante l'invio del comando al buzzer: {e}")
        else:
            print(f"  -> ATTENZIONE: La stanza '{room_name}' non esiste nel database.")
            
        return True