from typing import Dict, Any
from datetime import datetime, timezone
from src.services.base import BaseService

class PetStatisticsService(BaseService):
    """
    Servizio per calcolare le statistiche giornaliere del pet (es. violazioni e durata buzzer).
    Mantiene SOLO i dati del giorno corrente, resettando i contatori a mezzanotte.
    """

    def __init__(self):
        super().__init__()
        self.name = "PetStatisticsService"

    def execute(self, data: Dict, dr_type: str = "pet", attribute: str = None) -> Any:
        db_service = data.get("db_service")
        pet_id = data.get("pet_id")
        duration_minutes = float(data.get("duration_minutes", 0.0))
        violations_to_add = int(data.get("violations_to_add", 1))

        if not db_service or not pet_id:
            raise ValueError("db_service e pet_id sono obbligatori per aggiornare le statistiche del pet.")

        pet_dr = db_service.get_dr(dr_type=dr_type, dr_id=pet_id)
        if not pet_dr:
            raise ValueError(f"Pet con ID {pet_id} non trovato.")

        # 1. Calcoliamo la data di oggi a mezzanotte UTC
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        
        pet_data = pet_dr.get("data", {})
        daily_buzzer_stats = pet_data.get("daily_buzzer_stats", [])

        current_daily_stat = None

        # 2. Controlliamo se esiste già una statistica per OGGI
        if daily_buzzer_stats:
            last_stat = daily_buzzer_stats[0]
            stat_date = last_stat.get("date")
            
            is_today = False
            if isinstance(stat_date, datetime) and stat_date.date() == today.date():
                is_today = True
            elif isinstance(stat_date, str) and stat_date.startswith(today.strftime("%Y-%m-%d")):
                is_today = True

            if is_today:
                current_daily_stat = last_stat

        # 3. Logica di Incremento o Reset
        if current_daily_stat:
            current_daily_stat["auto_violations_count"] += violations_to_add
            current_daily_stat["auto_duration_mins"] += duration_minutes
            new_stats_list = [current_daily_stat]
        else:
            new_stats_list = [{
                "date": today,
                "auto_duration_mins": duration_minutes,
                "auto_violations_count": violations_to_add
            }]

        # 4. Aggiorniamo la Digital Replica del pet
        update_payload = {
            "data.daily_buzzer_stats": new_stats_list
        }
        db_service.update_dr(dr_type=dr_type, dr_id=pet_id, update_data=update_payload)

        return new_stats_list