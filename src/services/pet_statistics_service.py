from typing import Dict, Any
from datetime import datetime, timezone
from src.services.base import BaseService

class PetStatisticsService(BaseService):
    """
    Servizio per calcolare le statistiche giornaliere del pet (es. violazioni e durata buzzer).
    Mantiene i dati degli ultimi 30 giorni.
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

        is_today = False
        current_daily_stat = None

        # 2. Controlliamo se esiste già una statistica per OGGI
        if daily_buzzer_stats:
            last_stat = daily_buzzer_stats[0] 
            stat_date = last_stat.get("date") 
            
            # Gestione della data (potrebbe arrivare come dict da MongoDB, stringa o datetime)
            if isinstance(stat_date, dict) and "$date" in stat_date:
                if stat_date["$date"].startswith(today.strftime("%Y-%m-%d")):
                    is_today = True
            elif isinstance(stat_date, datetime) and stat_date.date() == today.date(): 
                is_today = True 
            elif isinstance(stat_date, str) and stat_date.startswith(today.strftime("%Y-%m-%d")): 
                is_today = True 

            if is_today:
                current_daily_stat = last_stat 

        # 3. Logica di Incremento o Aggiunta (Storico 30 giorni)
        if current_daily_stat:
            # Aggiorna i dati di oggi
            current_daily_stat["auto_violations_count"] += violations_to_add 
            current_daily_stat["auto_duration_mins"] += duration_minutes 
        else:
            # Crea un nuovo record per oggi e lo inserisce in testa alla lista
            new_stat = {
                "date": today,
                "auto_duration_mins": duration_minutes,
                "auto_violations_count": violations_to_add
            }
            daily_buzzer_stats.insert(0, new_stat)

        # 4. Mantiene solo gli ultimi 30 giorni (tronca la lista se supera i 30 elementi)
        daily_buzzer_stats = daily_buzzer_stats[:30]

        # 5. Aggiorniamo la Digital Replica del pet
        update_payload = {
            "data.daily_buzzer_stats": daily_buzzer_stats
        }
        db_service.update_dr(dr_type=dr_type, dr_id=pet_id, update_data=update_payload) 

        return daily_buzzer_stats