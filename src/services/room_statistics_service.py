from typing import Dict, Any
from datetime import datetime, timezone
from src.services.base import BaseService

class RoomStatisticsService(BaseService):
    """
    Servizio per calcolare le statistiche di occupazione della stanza.
    Mantiene SOLO i dati del giorno corrente, resettando i contatori a mezzanotte.
    """

    def __init__(self):
        super().__init__()
        self.name = "RoomStatisticsService"

    def execute(self, data: Dict, dr_type: str = "room", attribute: str = None) -> Any:
        db_service = data.get("db_service")
        room_id = data.get("room_id")
        duration_minutes = float(data.get("duration_minutes", 0.0))
        entries_to_add = int(data.get("entries_to_add", 1))

        if not db_service or not room_id:
            raise ValueError("db_service e room_id sono obbligatori per aggiornare le statistiche.")

        room_dr = db_service.get_dr(dr_type=dr_type, dr_id=room_id)
        if not room_dr:
            raise ValueError(f"Stanza con ID {room_id} non trovata.")

        # 1. Calcoliamo la data di oggi a mezzanotte UTC
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        
        room_data = room_dr.get("data", {})
        occupancy_stats = room_data.get("occupancy_stats", [])

        current_daily_stat = None

        # 2. Controlliamo se esiste già una statistica e se appartiene alla giornata di OGGI
        if occupancy_stats:
            last_stat = occupancy_stats[0]
            stat_date = last_stat.get("date")
            
            is_today = False
            if isinstance(stat_date, datetime) and stat_date.date() == today.date():
                is_today = True
            elif isinstance(stat_date, str) and stat_date.startswith(today.strftime("%Y-%m-%d")):
                is_today = True

            if is_today:
                current_daily_stat = last_stat

        # 3. Logica di Reset o Incremento
        if current_daily_stat:
            # Stesso giorno: incrementiamo i contatori
            current_daily_stat["dog_entries_count"] += entries_to_add
            current_daily_stat["daily_stay_duration_mins"] += duration_minutes
            new_stats_list = [current_daily_stat]
        else:
            # Nuovo giorno o primo avvio: resettiamo creando un nuovo record esclusivo per oggi
            new_stats_list = [{
                "date": today,
                "daily_stay_duration_mins": duration_minutes,
                "dog_entries_count": entries_to_add
            }]

        # 4. Aggiorniamo il Digital Replica della stanza sovrascrivendo l'array
        update_payload = {
            "data.occupancy_stats": new_stats_list
        }

        db_service.update_dr(dr_type=dr_type, dr_id=room_id, update_data=update_payload)

        return new_stats_list