#include <ESP8266WiFi.h>
#include <WiFiClientSecure.h> // Aggiunta la libreria per la connessione sicura TLS
#include <PubSubClient.h>

//const char *ssid = "FASTWEB-3QH6KF";
//const char *password = "E2XT6XK6JG";
const char *ssid = "OnePlus 8";
const char *password = "88888888";

// --- COORDINATE HIVEMQ CLOUD (PRIVATE) ---
const char* mqtt_server = "f91c2f750c5d4d2c9ff2177772a4ea75.s1.eu.hivemq.cloud";
const int mqtt_port = 8883;
const char* mqtt_user = "PetTracker";
const char* mqtt_password = "PetTracker26";

// Topic MQTT
const char* topic_pub_presenza = "casa/porta_u1";
const char* topic_lwt_stato    = "casa/porta_u1/stato";

#define TRIG_PIN D5 
#define ECHO_PIN D6

WiFiClientSecure espClient; // Sostituito il vecchio WiFiClient con la versione Secure
PubSubClient client(espClient);

long durata;
int distanza;

// --- VARIABILI PER LA LOGICA ADATTIVA ---
int distanzaPrecedente = -1;      
const int SOGLIA_VARIAZIONE = 10; 

unsigned long ultimoControllo = 0;
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
    
    // FONDAMENTALE PER HIVE MQ CLOUD: 
    // Dice al microcontrollore di accettare il certificato SSL del server.
    espClient.setInsecure();
  } else {
    Serial.println("\nTimeout WiFi. Riprovo al prossimo ciclo...");
  }
}

void tentaRiconnessioneMQTT() {
  if (millis() - ultimoTentativoMQTT > 5000) {
    ultimoTentativoMQTT = millis();
    Serial.print("Tentativo di connessione NodeMCU a MQTT (TLS)...");

    // Aggiunte le credenziali mqtt_user e mqtt_password alla chiamata connect()
    if (client.connect("NodeMCU-Ultrasuoni-Client", mqtt_user, mqtt_password, topic_lwt_stato, 1, true, "OFFLINE")) {
      Serial.println("connesso in sicurezza!");
      client.publish(topic_lwt_stato, "ONLINE", true);
    } else {
      Serial.print("fallito, rc=");
      Serial.println(client.state());
    }
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  WiFi.mode(WIFI_STA); 
  connettiWiFi();
  
  // Impostata la porta sicura (8883) invece della vecchia 1883
  client.setServer(mqtt_server, mqtt_port);
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    connettiWiFi();
    return; 
  }

  if (!client.connected()) {
    tentaRiconnessioneMQTT();
    return; 
  }
  
  client.loop();

  if (millis() - ultimoControllo > 500) {
    ultimoControllo = millis();
    
    digitalWrite(TRIG_PIN, LOW);
    delayMicroseconds(2);
    digitalWrite(TRIG_PIN, HIGH);
    delayMicroseconds(10);
    digitalWrite(TRIG_PIN, LOW);
    
    durata = pulseIn(ECHO_PIN, HIGH);
    distanza = durata * 0.034 / 2;

    Serial.printf("Distanza attuale: %d cm | Precedente: %d cm\n", distanza, (distanzaPrecedente == -1 ? 0 : distanzaPrecedente));

    if (distanza > 0) {
      if (distanzaPrecedente != -1) {
        int differenza = distanzaPrecedente - distanza;

        if (differenza >= SOGLIA_VARIAZIONE) { 
          Serial.println("[MQTT] Movimento rilevato! Avviso le Camere...");
          client.publish(topic_pub_presenza, "ACCENDI_CAMERA");
          delay(5000); 
          distanzaPrecedente = -1;
        } else {
          distanzaPrecedente = distanza;
        }
      } else {
        distanzaPrecedente = distanza;
      }
    }
  }
}