from digital_replica.dr_factory import DRFactory

# =====================================================================
# BLOCCO DI TEST UNITARIO E DOCUMENTAZIONE DEL TEST
# =====================================================================
"""
COSA CONSISTE QUESTO TEST E COSA SIGNIFICA L'OUTPUT:

Il test serve a verificare che la DRFactory applichi correttamente le regole 
di validazione dinamica definite nello schema YAML (es. templates/wine.yaml).
In particolare, verifica che il sistema accetti i dati corretti e blocchi i 
"dati invalidi" (dati che violano i vincoli di tipo, i limiti min/max o i campi obbligatori).

I TEST EFFETTUATI SONO TRE:

1. TEST 1 (Dati Validi): 
   Si passano dati coerenti (es. vintage 2021, temperatura 16.5).
   - Obiettivo: Verificare che il record venga creato con successo, generando 
     _id, timestamp e inserendo i campi nel profilo e nei dati.

2. TEST 2 (Dati Invalidi - Limiti Numerici): 
   Si forza il sistema con dati fuori scala (vintage 1850 e temperatura 25.0).
   - Regola YAML: Il vintage deve essere >= 1900, la temperatura <= 20.
   - Obiettivo: Verificare che Pydantic blocchi i dati. L'output mostra infatti 
     "greater_than_equal" e "less_than_equal". Il blocco è il comportamento CORRETTO.

3. TEST 3 (Dati Invalidi - Struttura della Lista): 
   Si invia una misurazione nei 'measurements' inserendo il timestamp ma 
   omettendo la chiave 'temperature'.
   - Regola YAML: Ogni elemento della lista deve contenere sia timestamp che temperature.
   - Obiettivo: Verificare che il validatore dinamico 'validate_list_items' intercetti 
     l'assenza della chiave. L'output mostra infatti "Missing required fields ['temperature']".

NOTA SULL'OUTPUT DEL TERMINALE:
I messaggi di errore stampati sotto il Test 2 e il Test 3 NON indicano un malfunzionamento 
del programma, ma confermano che i sistemi di sicurezza hanno intercettato e respinto 
i dati malformati prima di salvarli. Il "Process finished with exit code 0" finale indica 
che tutta la suite di test è stata completata senza crash imprevisti.
"""

if __name__ == "__main__":
    print("=== INIZIO TEST SU DRFACTORY (WINE_BOTTLE) ===")

    path_schema = r"templates\wine.yaml"

    try:
        factory = DRFactory(path_schema)
        print(f"✓ Schema caricato correttamente da: {path_schema}")
    except Exception as e:
        print(f"✗ Fallito caricamento schema: {e}")
        exit()

    # -----------------------------------------------------------------
    # TEST 1: Creazione Digital Replica con dati corretti
    # -----------------------------------------------------------------
    print("\n--- Test 1: Creazione record valido ---")
    vino_valido = {
        "profile": {
            "wine_name": "Sassicaia",
            "wine_producer": "Tenuta San Guido",
            "vintage": 2021,
            "optimal_temperature": 16.5
        },
        "data": {
            "measurements": [
                {"timestamp": "2026-07-11T12:00:00", "temperature": 16.0}
            ]
        }
    }

    try:
        dr_vino = factory.create_dr(dr_type="wine_bottle", initial_data=vino_valido)
        print("✓ Digital Replica generata con successo!")
        print(f"  ID Generato: {dr_vino['_id']}")
        print(f"  Profilo inserito: {dr_vino['profile']}")
        print(f"  Dati Inizializzati: {dr_vino['data']}")
        print(f"  Metadata: {dr_vino['metadata']}")
    except Exception as e:
        print(f"✗ Errore imprevisto nel Test 1: {e}")

    # -----------------------------------------------------------------
    # TEST 2: Violazione vincoli numerici (Min/Max)
    # -----------------------------------------------------------------
    print("\n--- Test 2: Inserimento dati fuori limite (Vintage e Temperatura errati) ---")
    vino_errato_limiti = {
        "profile": {
            "wine_name": "Tignanello",
            "vintage": 1850,
            "optimal_temperature": 25.0
        }
    }

    try:
        factory.create_dr(dr_type="wine_bottle", initial_data=vino_errato_limiti)
        print("✗ Errore: La factory ha accettato dati numerici fuori dai limiti!")
    except Exception as e:
        print("✓ Validazione Pydantic riuscita! I limiti min/max hanno bloccato i dati.")
        print(f"  Messaggio di errore catturato:\n  {e}")

    # -----------------------------------------------------------------
    # TEST 3: Struttura errata della lista di dizionari (Measurements)
    # -----------------------------------------------------------------
    print("\n--- Test 3: Validazione campi obbligatori nei sensori (Manca 'temperature') ---")
    vino_sensore_incompleto = {
        "profile": {
            "wine_name": "Barolo",
            "optimal_temperature": 18.0
        },
        "data": {
            "measurements": [
                {"timestamp": "2026-07-11T12:05:00"}
            ]
        }
    }

    try:
        factory.create_dr(dr_type="wine_bottle", initial_data=vino_sensore_incompleto)
        print("✗ Errore: La factory ha accettato un sensore privo del campo obbligatorio!")
    except Exception as e:
        print("✓ Validazione interna riuscita! Il validatore 'validate_list_items' ha intercettato la chiave mancante.")
        print(f"  Messaggio di errore catturato:\n  {e}")

    print("\n=== FINE VERIFICHE ===")
