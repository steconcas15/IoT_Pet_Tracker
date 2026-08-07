#include <ESP8266WiFi.h>
#include <WiFiClientSecure.h> 
#include <PubSubClient.h>

// --- CREDENZIALI WIFI ---
const char *ssid = "OnePlus 8";
const char *password = "88888888";

// --- COORDINATE HIVEMQ CLOUD (PRIVATE) ---
const char* mqtt_server = "f91c2f750c5d4d2c9ff2177772a4ea75.s1.eu.hivemq.cloud";
const int mqtt_port = 8883;
const char* mqtt_user = "PetTracker";
const char* mqtt_password = "PetTracker26";

// --- TOPIC MQTT ---
const char* topic_sub_buzzer = "casa/sound";
const char* topic_lwt_stato  = "casa/buzzer/stato"; // Nuovo topic per lo stato LWT

#define BUZZER_PIN D0

WiFiClientSecure espClient; 
PubSubClient client(espClient);

unsigned long ultimoTentativoMQTT = 0;

void connettiWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  
  Serial.print("\nConnessione WiFi a ");
  Serial.print(ssid);
  
  WiFi.disconnect(); 
  delay(100);
  WiFi.begin(ssid, password);
  
  int tentativi = 0;
  while (WiFi.status() != WL_CONNECTED && tentativi < 20) {
    delay(500);
    Serial.print(".");
    tentativi++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi Connesso!");
    
    // Accetta il certificato SSL del server HiveMQ
    espClient.setInsecure();
  } else {
    Serial.println("\nTimeout WiFi. Riprovo al prossimo ciclo...");
  }
}

void callback(char* topic, byte* payload, unsigned int length) {
  String messaggio = "";
  for (unsigned int i = 0; i < length; i++) {
    messaggio += (char)payload[i];
  }
  
  Serial.print("Messaggio ricevuto sul topic: ");
  Serial.println(topic);
  
  if (String(topic) == topic_sub_buzzer) {
    if (messaggio == "ON" || messaggio == "1") {
      Serial.println("CANE RILEVATO IN STANZA VIETATA! Attivazione Buzzer continua!");
      digitalWrite(BUZZER_PIN, HIGH); // Il buzzer suona e resta acceso
    } 
    else if (messaggio == "OFF" || messaggio == "0") {
      Serial.println("CANE USCITO. Disattivazione Buzzer.");
      digitalWrite(BUZZER_PIN, LOW);  // Il buzzer si spegne
    }
  }
}

void tentaRiconnessioneMQTT() {
  if (millis() - ultimoTentativoMQTT > 5000) {
    ultimoTentativoMQTT = millis();
    Serial.print("Tentativo di connessione NodeMCU-Buzzer a MQTT (TLS)...");

    // Connessione con LWT: se il dispositivo si scollega in modo anomalo, il broker pubblica "OFFLINE"
    if (client.connect("NodeMCU-Buzzer-Client", mqtt_user, mqtt_password, topic_lwt_stato, 1, true, "OFFLINE")) {
      Serial.println("connesso in sicurezza!");
      
      // Pubblica lo stato ONLINE al momento della connessione riuscita
      client.publish(topic_lwt_stato, "ONLINE", true);
      
      // Iscrizione al topic di comando del server
      client.subscribe(topic_sub_buzzer);
    } else {
      Serial.print("fallito, rc=");
      Serial.println(client.state());
    }
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW); // Assicuriamoci che parta spento

  WiFi.mode(WIFI_STA); 
  connettiWiFi();
  
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);
}

void loop() {
  // Mantieni attiva la connessione WiFi
  if (WiFi.status() != WL_CONNECTED) {
    connettiWiFi();
    return; 
  }

  // Mantieni attiva la connessione MQTT
  if (!client.connected()) {
    tentaRiconnessioneMQTT();
    return; 
  }
  
  // Elabora i messaggi in entrata
  client.loop();
}