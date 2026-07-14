import pprint
# Importiamo la classe dal file aggiornato
from digital_replica.schema_registry import SchemaRegistry

def esegui_test():
    registry = SchemaRegistry()
    
    # DATI DI CONFIGURAZIONE (Cambia i nomi se sono diversi)
    NOME_SCHEMA = "wine" 
    PATH_YAML = r"templates\wine.yaml"  # <--- Metti il nome esatto del tuo file YAML
    
    print(f"--- 🚀 Avvio Test di Conversione per: {PATH_YAML} ---")
    try:
        # 1. Carica e converti lo schema
        registry.load_schema(NOME_SCHEMA, PATH_YAML)
        print("✅ Successo! Il file YAML è stato letto e convertito senza errori.\n")
        
        # 2. Estrai lo schema generato per MongoDB
        schema_finale = registry.get_validation_schema(NOME_SCHEMA)
        
        # 3. Mostra il nome della collezione generata
        print("--- 📦 Nome Collezione MongoDB ---")
        print(f"Nome: {registry.get_collection_name(NOME_SCHEMA)}\n")
        
        # 4. Mostra la struttura generata
        print("--- 📋 Struttura $jsonSchema Generata ---")
        pprint.pprint(schema_finale, indent=2, width=100)
        
        # Verifica veloce dei requisiti interni
        print("\n--- 🔍 Verifica dei Sotto-Campi Obbligatori ---")
        props = schema_finale["$jsonSchema"]["properties"]
        if "profile" in props and "required" in props["profile"]:
            print(f"🔹 Campi obbligatori in 'profile': {props['profile']['required']}")
        if "metadata" in props and "required" in props["metadata"]:
            print(f"🔹 Campi obbligatori in 'metadata': {props['metadata']['required']}")

    except Exception as e:
        print(f"❌ Errore durante il test: {e}")

if __name__ == "__main__":
    esegui_test()
