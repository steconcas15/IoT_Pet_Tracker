#include <ESP8266WiFi.h>
#include <WiFiClientSecure.h> // Secure TLS connection library
#include <PubSubClient.h>

// --- WIFI CONFIGURATION ---
const char *ssid = "FASTWEB-3QH6KF";
const char *password = "E2XT6XK6JG";

// --- HIVEMQ CLOUD COORDINATES (PRIVATE) ---
const char* mqtt_server = "f91c2f750c5d4d2c9ff2177772a4ea75.s1.eu.hivemq.cloud";
const int mqtt_port = 8883;
const char* mqtt_user = "PetTracker";
const char* mqtt_password = "PetTracker26";

// --- MQTT TOPICS (Kept in Italian as requested) ---
const char* topic_pub_presence = "casa/porta_u1";
const char* topic_lwt_status   = "casa/porta_u1/stato";

#define TRIG_PIN D5 
#define ECHO_PIN D6

WiFiClientSecure espClient; 
PubSubClient client(espClient);

long duration;
int distance;

// --- ADAPTIVE LOGIC VARIABLES ---
int previousDistance = -1;      
const int VARIATION_THRESHOLD = 10; 

// Variable to track if the pet is currently lingering under the door
bool petUnderDoor = false; 

unsigned long lastCheck = 0;
unsigned long lastMqttAttempt = 0;

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
    Serial.print("Attempting MQTT (TLS) connection...");

    if (client.connect("NodeMCU-Ultrasonic-Client-Door1", mqtt_user, mqtt_password, topic_lwt_status, 1, true, "OFFLINE")) {
      Serial.println("Securely connected!");
      // Publish the LWT status as ONLINE with the retained flag set to true
      client.publish(topic_lwt_status, "ONLINE", true);
    } else {
      Serial.print("Failed, rc=");
      Serial.println(client.state());
    }
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  WiFi.mode(WIFI_STA); 
  connectWiFi();
  
  client.setServer(mqtt_server, mqtt_port);
}

void loop() {
  // Check and maintain network connections
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
    return; 
  }

  if (!client.connected()) {
    attemptMqttReconnection();
    return; 
  }
  
  client.loop();

  // Sampling frequency: 2 Hz (every 500 ms)
  if (millis() - lastCheck > 500) {
    lastCheck = millis();
    
    // Trigger ultrasonic pulse
    digitalWrite(TRIG_PIN, LOW);
    delayMicroseconds(2);
    digitalWrite(TRIG_PIN, HIGH);
    delayMicroseconds(10);
    digitalWrite(TRIG_PIN, LOW);
    
    // Read the echo and calculate distance
    duration = pulseIn(ECHO_PIN, HIGH);
    distance = duration * 0.034 / 2;

    Serial.printf("Current Distance: %d cm | Previous: %d cm\n", distance, (previousDistance == -1 ? 0 : previousDistance));

    if (distance > 0) {
      if (previousDistance != -1) {
        
        // Calculate the delta (Positive = distance decreased, Negative = distance increased)
        int delta = previousDistance - distance;

        if (!petUnderDoor && delta >= VARIATION_THRESHOLD) { 
          // POSITIVE DELTA: Pet entered the sensor range
          petUnderDoor = true;
          Serial.println("[STATUS] Positive Delta: Pet entered the door frame. Waiting for exit...");
        } 
        else if (petUnderDoor && delta <= -VARIATION_THRESHOLD) {
          // NEGATIVE DELTA: Pet left the sensor range (distance increased back to normal)
          petUnderDoor = false;
          Serial.println("[STATUS] Negative Delta: Pet successfully crossed! Sending MQTT trigger...");
          
          // Publish the trigger with the RETAINED flag set to true to ensure delivery
          client.publish(topic_pub_presence, "TURN_ON_CAMERA", true);
        }
        else if (petUnderDoor && abs(delta) < VARIATION_THRESHOLD) {
          // LINGERING: Pet is standing still under the door (distance hasn't changed much)
          Serial.println("[STATUS] Pet is lingering under the door. No trigger sent yet.");
        }
      }
      
      // Save current reading for the next cycle comparison
      previousDistance = distance;
    }
  }
}