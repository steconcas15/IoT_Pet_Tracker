from config_loader import ConfigLoader
# Importiamo il servizio che gestisce il database dal tuo progetto
from src.services.database_service import DatabaseService

try:
    print("--- TEST DI CONNESSIONE REALE ---")

    # 1. Carica la configurazione e crea la stringa
    db_config = ConfigLoader.load_database_config("database.yaml")
    connection_string = ConfigLoader.build_connection_string(db_config)

    # 2. Inizializza il servizio database
    # (Nota: passiamo None a schema_registry per questo test veloce se non lo abbiamo pronto)
    db_service = DatabaseService(
        connection_string=connection_string,
        db_name=db_config["settings"]["name"],
        schema_registry=None
    )

    # 3. Prova a connetterti!
    print("Tentativo di connessione a MongoDB in corso...")
    db_service.connect()

    # Se arriviamo qui senza errori, siamo connessi!
    print("-> CONNESSO CON SUCCESSO! Il database risponde correttamente. 🎉")

    # Scolleghiamoci in modo pulito
    db_service.disconnect()
    print("Disconnesso in modo pulito.")

except Exception as e:
    print(f"\n[ERRORE DI CONNESSIONE]: Impossibile connettersi al database!")
    print(f"Dettaglio errore: {e}")