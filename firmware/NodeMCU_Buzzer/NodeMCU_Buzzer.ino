#include <ESP8266WiFi.h>
#include <WiFiClientSecure.h> // Secure TLS connection library
#include <MQTT.h>             // Replaced PubSubClient to support QoS 1 publishing

// --- WIFI CONFIGURATION ---
const char *ssid = "FASTWEB-3QH6KF";
const char *password = "E2XT6XK6JG";

// --- DIGITAL TWIN IDENTIFIERS ---
const char* pet_id = "8feecdf5-8aec-4720-9196-6d1d9189c502";

// --- HIVEMQ CLOUD COORDINATES (PRIVATE) ---
const char* mqtt_server = "f91c2f750c5d4d2c9ff2177772a4ea75.s1.eu.hivemq.cloud";
const int mqtt_port = 8883;
const char* mqtt_user = "PetTracker";
const char* mqtt_password = "PetTracker26";

// --- MQTT TOPICS ---
const char* topic_sub_buzzer = "home/sound";
// LWT status topic dynamically generated using the unique pet_id
String topic_lwt_status = String("home/") + pet_id + "/state"; 

#define BUZZER_PIN D0

// --- GLOBAL VARIABLES ---
WiFiClientSecure espClient; 
MQTTClient mqttClient(256); // Buffer size for MQTT payloads

unsigned long lastMqttAttempt = 0;

// --- FUNCTION DECLARATIONS ---
void connectWiFi();
void attemptMqttReconnection();
void mqttCallback(String &topic, String &payload);

void setup() {
  Serial.begin(115200);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW); // Ensure it starts turned off

  Serial.println("\n[STATUS] Starting NodeMCU Buzzer MQTT (TLS/SSL + QoS 1)...");

  WiFi.mode(WIFI_STA); 
  connectWiFi();
  
  mqttClient.begin(mqtt_server, mqtt_port, espClient);
  mqttClient.onMessage(mqttCallback);
}

void loop() {
  // Check and maintain network connections
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
    return; 
  }

  // Check and maintain MQTT connection
  if (!mqttClient.connected()) {
    attemptMqttReconnection();
    return; 
  }
  
  // Process incoming messages
  mqttClient.loop();
}

// --- NETWORK AND MQTT LOGIC ---

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  
  Serial.print("\nConnecting to WiFi: ");
  Serial.print(ssid);
  
  WiFi.disconnect(); 
  delay(100);
  WiFi.begin(ssid, password);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi Connected!");
    
    // REQUIRED FOR HIVE MQ CLOUD: 
    // Instructs the microcontroller to accept the server's SSL certificate without validation.
    espClient.setInsecure();
  } else {
    Serial.println("\nWiFi Timeout. Retrying on next cycle...");
  }
}

void attemptMqttReconnection() {
  if (millis() - lastMqttAttempt > 5000) {
    lastMqttAttempt = millis();
    Serial.print("[STATUS] Attempting MQTT (TLS) connection...");

    // Setup Last Will and Testament (LWT) BEFORE connecting
    // QoS = 1, Retained = true
    mqttClient.setWill(topic_lwt_status.c_str(), "OFFLINE", true, 1);

    // Attempt connection with Authentication (User/Pass)
    if (mqttClient.connect("NodeMCU-Buzzer-Client", mqtt_user, mqtt_password)) {
      Serial.println("Securely connected!");
      
      // Publish the ONLINE status with the retained flag set to true (QoS 1)
      mqttClient.publish(topic_lwt_status.c_str(), "ONLINE", true, 1);
      
      // Subscribe to the server command topic with QoS 1
      mqttClient.subscribe(topic_sub_buzzer, 1);
      Serial.printf("[STATUS] Subscribed to topic: %s\n", topic_sub_buzzer);
    } else {
      Serial.print("Failed, return code = ");
      Serial.println(mqttClient.returnCode());
    }
  }
}

void mqttCallback(String &topic, String &payload) {
  Serial.printf("[STATUS] Message received on topic: %s\n", topic.c_str());
  
  if (topic == String(topic_sub_buzzer)) {
    if (payload == "ON" || payload == "1") {
      Serial.println("[BUZZER] DOG DETECTED IN FORBIDDEN ROOM! Continuous Buzzer activated!");
      digitalWrite(BUZZER_PIN, HIGH); // Turn the buzzer on and leave it on
    } 
    else if (payload == "OFF" || payload == "0") {
      Serial.println("[BUZZER] DOG LEFT. Buzzer deactivated.");
      digitalWrite(BUZZER_PIN, LOW);  // Turn the buzzer off
    }
  }
}