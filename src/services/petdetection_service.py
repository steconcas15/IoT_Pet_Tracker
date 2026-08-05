from src.services.base import BaseService
# Importiamo il servizio delle statistiche per invocarlo al bisogno
from src.services.room_statistics_service import RoomStatisticsService
from bson import ObjectId
import os
from flask import current_app
from datetime import datetime, timezone
from bot.notifier import send_unauthorized_room_alert

class PetDetectionService(BaseService):
    """
    Servizio per il rilevamento del pet tramite YOLO e l'aggiornamento
    dello stato del Digital Twin e delle statistiche di permanenza.
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
            
            # Non facciamo assolutamente nulla.
            # La stanza mantiene lo status "occupied", il timer continua a girare,
            # e il pet mantiene la sua ultima posizione nota.
            # L'uscita (e il calcolo delle statistiche) avverrà solo nella LOGICA 2,
            # quando il pet verrà rilevato positivamente in una NUOVA stanza.
                
            return False

        # =====================================================================
        # LOGICA 2: PET RILEVATO
        # =====================================================================
        print(f"[PetDetectionService] POSITIVO: Pet identificato in '{room_name}'!")
        
        # Se il pet è in una NUOVA stanza rispetto a prima
        if previous_room != room_name:
            
            # STEP 1: Fai uscire il pet dalla vecchia stanza (calcolando le statistiche)
            if previous_room:
                self._handle_pet_exit(previous_room, db_service)
                
            # STEP 2: Fai entrare il pet nella nuova stanza (avviando il timer)
            self._handle_pet_entry(room_name, db_service)
            
            # STEP 3: Aggiorna la posizione attuale sulla DR del pet
            db_service.update_dr("pet", pet_id, {"data.current_room": room_name})
            print(f"  -> DB Pet: 'current_room' aggiornata a '{room_name}'.")
            
            # STEP 4: Gestione MQTT / Allarmi
            self._trigger_alarms(room_name, db_service, str(pet_id))
            
        return True

    # -------------------------------------------------------------------------
    # METODI DI APPOGGIO (HELPER)
    # -------------------------------------------------------------------------

    def _handle_pet_exit(self, room_name: str, db_service):
            """Gestisce l'uscita da una stanza: calcola il tempo e aggiorna le statistiche."""
            rooms = db_service.query_drs("room", {"profile.name": room_name})
            if not rooms:
                return
                
            room_data = rooms[0]
            room_id = room_data["_id"]
            current_status = room_data.get("data", {}).get("status", "empty")

            if current_status == "occupied":
                last_entry_time = room_data.get("data", {}).get("last_entry_time")
                duration_minutes = 0.0

                # Calcolo dei minuti passati dall'ingresso
                if last_entry_time:
                    # 1. Se arriva come stringa, la parsiamo assegnando il fuso orario
                    if isinstance(last_entry_time, str):
                        last_entry_time = datetime.fromisoformat(last_entry_time.replace("Z", "+00:00"))
                    # 2. FIX: Se arriva come datetime da MongoDB (naive), forziamo il fuso orario UTC
                    elif isinstance(last_entry_time, datetime) and last_entry_time.tzinfo is None:
                        last_entry_time = last_entry_time.replace(tzinfo=timezone.utc)

                    # Ora entrambe le date sono "offset-aware" e la sottrazione funzionerà
                    time_diff = datetime.now(timezone.utc) - last_entry_time
                    duration_minutes = time_diff.total_seconds() / 60.0

                # 1. Invochiamo il servizio statistiche per sommare la permanenza
                stats_service = RoomStatisticsService()
                stats_service.execute({
                    "db_service": db_service,
                    "room_id": str(room_id),
                    "duration_minutes": duration_minutes,
                    "entries_to_add": 1
                })

                # 2. Resettiamo lo stato della stanza e puliamo il timer
                db_service.update_dr("room", str(room_id), {
                    "data.status": "empty",
                    "data.last_entry_time": None
                })
                print(f"  -> DB Stanza: '{room_name}' liberata. Statistiche aggiornate ({duration_minutes:.2f} min).")


    def _handle_pet_entry(self, room_name: str, db_service):
        """Gestisce l'ingresso in una stanza: imposta occupato e avvia il timer."""
        rooms = db_service.query_drs("room", {"profile.name": room_name})
        if not rooms:
            print(f"  -> ATTENZIONE: La stanza '{room_name}' non esiste nel database.")
            return
            
        room_data = rooms[0]
        room_id = room_data["_id"]

        db_service.update_dr("room", str(room_id), {
            "data.status": "occupied",
            "data.last_entry_time": datetime.now(timezone.utc)
        })
        print(f"  -> DB Stanza: '{room_name}' occupata. Timer avviato.")


    def _trigger_alarms(self, room_name: str, db_service, pet_id: str):
        """Controlla i permessi della stanza e invia gli eventuali allarmi MQTT e notifiche Telegram."""
        rooms = db_service.query_drs("room", {"profile.name": room_name})
        if not rooms:
            return
            
        permission_level = rooms[0].get("profile", {}).get("permission_level", "allowed")
        pet_dr = db_service.get_dr("pet", pet_id)
        last_buzzer_start = pet_dr.get("data", {}).get("last_buzzer_start_time")
        
        # Gestione accensione allarme (ON)
        if permission_level == "forbidden":
            if not last_buzzer_start:
                db_service.update_dr("pet", pet_id, {
                    "data.last_buzzer_start_time": datetime.now(timezone.utc)
                })
                
            # 1. Attivazione Buzzer via MQTT
            if hasattr(current_app, 'mqtt_manager'):
                try:
                    current_app.mqtt_manager.client.publish("casa/sound", "ON")
                    print(f"  -> 🚨 ALLARME: Il pet è in una stanza vietata ({room_name})! Attivazione buzzer.")
                except Exception as e:
                    print(f"  -> [MQTT] Errore: {e}")

            # 2. Invio notifica istantanea su Telegram
            try:
                send_unauthorized_room_alert(room_name)
                print(f"  -> 📲 TELEGRAM: Notifica di intrusione inviata per la stanza {room_name}.")
            except Exception as e:
                print(f"  -> [TELEGRAM] Errore invio notifica: {e}")

        # Gestione spegnimento allarme (OFF)
        elif permission_level == "allowed":
            if last_buzzer_start:
                duration_minutes = 0.0
                
                if isinstance(last_buzzer_start, str):
                    last_buzzer_start = datetime.fromisoformat(last_buzzer_start.replace("Z", "+00:00"))
                elif isinstance(last_buzzer_start, datetime) and last_buzzer_start.tzinfo is None:
                    last_buzzer_start = last_buzzer_start.replace(tzinfo=timezone.utc)
                    
                time_diff = datetime.now(timezone.utc) - last_buzzer_start
                duration_minutes = time_diff.total_seconds() / 60.0
                
                # Invochiamo il PetStatisticsService
                from src.services.pet_statistics_service import PetStatisticsService
                stats_service = PetStatisticsService()
                stats_service.execute({
                    "db_service": db_service,
                    "pet_id": str(pet_id),
                    "duration_minutes": duration_minutes,
                    "violations_to_add": 1
                })
                
                db_service.update_dr("pet", pet_id, {
                    "data.last_buzzer_start_time": None
                })
            
            if hasattr(current_app, 'mqtt_manager'):
                try:
                    current_app.mqtt_manager.client.publish("casa/sound", "OFF")
                    print(f"  -> ✅ Stanza sicura ({room_name}). Disattivazione buzzer.")
                except Exception as e:
                    print(f"  -> [MQTT] Errore: {e}")