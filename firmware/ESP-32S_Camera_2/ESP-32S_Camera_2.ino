/**
 * ESP32-CAM Digital Twin IoT Telemetry Firmware
 * =============================================
 * This firmware manages an ESP32-CAM device functioning as a spatial sensor node.
 * It connects to a secure Wi-Fi network, performs automated JSON Web Token (JWT) 
 * authentication with a backend server, maintains a persistent TLS-secured MQTT connection 
 * (with Last Will and Testament support), and handles high-resolution image capture 
 * and HTTP multipart telemetry streaming upon receiving trigger events.
 */

#include <Arduino.h>
#include "esp_camera.h"
#include <WiFi.h>
#include <WiFiClientSecure.h> // Secure TLS connection library
#include <MQTT.h> 
#include <HTTPClient.h>
#include <ArduinoJson.h>

// --- HARDWARE CONFIGURATION ---
#include "board_config.h"

// --- WIFI CONFIGURATION ---
const char *ssid = "FASTWEB-3QH6KF";
const char *password = "E2XT6XK6JG";

// --- DIGITAL TWIN IDENTIFIERS ---
const char* home_id = "6a6b0e2a73e73970ad552f46"; 
const char* room_id = "6b1a6338-746b-4a8f-a99c-7cbf09bd595b"; 
const char* door_id = "7d0b2bd9-8320-4337-a0c0-f8aedc9f118c";

// --- HIVEMQ CLOUD COORDINATES (PRIVATE) ---
const char* mqtt_server = "f91c2f750c5d4d2c9ff2177772a4ea75.s1.eu.hivemq.cloud"; 
const int mqtt_port = 8883; 
const char* mqtt_user = "PetTracker";
const char* mqtt_password = "PetTracker26";

// --- MQTT TOPICS ---
// LWT status topic dynamically generated using the unique room_id
String topic_lwt_status  = String("home/") + room_id + "/state"; 
// Subscription topic dynamically generated using the unique door_id
String topic_sub_trigger = String("home/") + door_id; 

// --- HTTP SERVER CONFIGURATION ---
const char* server_ip = "192.168.1.64"; 
const int server_port = 5000; 

// --- GLOBAL VARIABLES ---
WiFiClientSecure espClient; 
MQTTClient mqttClient(512); // Buffer size for MQTT payloads

unsigned long lastMqttAttempt = 0; 
String jwtToken = ""; // Dynamic JWT token storage

// --- FUNCTION DECLARATIONS ---
void setupCamera();
void connectWiFi();
bool loginToServer();
void attemptMqttReconnection();
void mqttCallback(String &topic, String &payload);
void takeAndSendPhoto();

void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(true);
  Serial.println("\n[STATUS] Starting ESP32-CAM MQTT (TLS/SSL + Multipart + JWT Auth + QoS 1)...");

  setupCamera();
  connectWiFi();

  mqttClient.begin(mqtt_server, mqtt_port, espClient);
  mqttClient.onMessage(mqttCallback);
}

void loop() {
  // Check and maintain active network connections
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
    return; 
  }

  if (!mqttClient.connected()) {
    attemptMqttReconnection();
    return; 
  }
  
  mqttClient.loop();
  delay(10); 
}

// --- NETWORK AND AUTHENTICATION LOGIC ---

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  
  Serial.print("\nConnecting to Wi-Fi network: ");
  Serial.print(ssid);
  
  WiFi.disconnect(); 
  delay(100);
  WiFi.begin(ssid, password);
  WiFi.setSleep(false);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWi-Fi Successfully Connected!");
    Serial.print("Assigned IP Address: ");
    Serial.println(WiFi.localIP());
    
    // REQUIRED FOR HIVEMQ CLOUD: 
    // Instructs the microcontroller to bypass strict SSL certificate validation chains.
    espClient.setInsecure();

    // Block execution until a valid JWT token is successfully acquired from the API
    while (jwtToken == "") {
      loginToServer();
      if (jwtToken == "") {
        Serial.println("[AUTH] Authentication timeout. Retrying login sequence in 5 seconds...");
        delay(5000);
      }
    }
  } else {
    Serial.println("\nWi-Fi Connection Timeout. Retrying on next scheduling cycle...");
  }
}

bool loginToServer() {
  if (WiFi.status() != WL_CONNECTED) return false;

  WiFiClient localClient; // Standard unencrypted client for local network traffic
  HTTPClient http;
  
  // Dynamic URL construction embedding the room_id directly into the REST path (/api/dr/<dr_id>/tokens)
  String auth_url = String("http://") + server_ip + ":" + server_port + "/api/dr/" + room_id + "/tokens";
  
  Serial.println("[AUTH] Requesting JWT access token from the local server...");
  http.begin(localClient, auth_url); 
  
  // No payload body required; strictly a RESTful path parameter authentication request
  http.addHeader("Content-Length", "0");
  
  int httpResponseCode = http.POST("");

  if (httpResponseCode == 200) {
    String response = http.getString();
    
    StaticJsonDocument<512> doc;
    DeserializationError error = deserializeJson(doc, response);

    if (!error) {
      const char* token = doc["access_token"];
      jwtToken = String(token);
      
      Serial.println("[AUTH] Authentication complete! JWT successfully retrieved.");
      http.end();
      return true;
    } else {
      Serial.println("[AUTH] Error parsing server authentication JSON response.");
    }
  } else {
    Serial.printf("[AUTH] Login failed. Response HTTP Code: %d\n", httpResponseCode);
  }
  
  http.end();
  return false;
}

void attemptMqttReconnection() {
  if (millis() - lastMqttAttempt > 5000) {
    lastMqttAttempt = millis();
    Serial.print("[STATUS] Attempting secure MQTT (TLS) broker connection...");
    
    String clientID = "ESP32CAM-" + String((uint32_t)ESP.getEfuseMac(), HEX);

    // Configure Last Will and Testament (LWT) parameters BEFORE establishing connection
    // QoS = 1, Retained = true. Utilizes dynamically generated topic_lwt_status
    mqttClient.setWill(topic_lwt_status.c_str(), "OFFLINE", true, 1);

    // Attempt connection utilizing user credentials
    if (mqttClient.connect(clientID.c_str(), mqtt_user, mqtt_password)) {
      Serial.println(" Securely connected!");
      
      // Publish initial LWT status as ONLINE with retain flag set to true (QoS 1)
      mqttClient.publish(topic_lwt_status.c_str(), "ONLINE", true, 1);
      
      // Subscribe to the ultrasonic sensor trigger topic with QoS 1
      mqttClient.subscribe(topic_sub_trigger.c_str(), 1);
      Serial.printf("[STATUS] Successfully subscribed to topic: %s\n", topic_sub_trigger.c_str());
    } else {
      Serial.print("Connection failed, return code (rc) = ");
      Serial.println(mqttClient.returnCode());
    }
  }
}

void mqttCallback(String &topic, String &payload) {
  Serial.printf("[STATUS] Incoming message on topic: %s | Payload: %s\n", topic.c_str(), payload.c_str());
  
  if (topic == topic_sub_trigger && payload == "TURN_ON_CAMERA") {
    Serial.println("[STATUS] Trigger event received! Initializing camera capture sequence...");
    takeAndSendPhoto();
  }
}

// --- CAMERA AND HTTP MULTIPART LOGIC ---

void takeAndSendPhoto() {
  camera_fb_t * fb = NULL; 
  sensor_t * s = esp_camera_sensor_get(); 

  // Evaluate current exposure value to determine if supplementary flash lighting is needed
  int aec_value = s->status.aec_value; 
  Serial.printf("[CAMERA] Current exposure value (AEC): %d\n", aec_value);
  bool needFlash = (aec_value > 800); 

  if (needFlash) {
    Serial.println("[CAMERA] Low-light environment detected: Activating hardware flash.");
    #if defined(LED_GPIO_NUM)
      ledcWrite(LED_GPIO_NUM, 255); 
      delay(200);                   
    #endif
  }

  // Trigger camera shutter to capture frame buffer
  fb = esp_camera_fb_get(); 

  #if defined(LED_GPIO_NUM)
    ledcWrite(LED_GPIO_NUM, 0);
  #endif

  if (!fb) {
    Serial.println("[CAMERA] Error: Frame buffer capture failed.");
    return;
  }
  Serial.printf("[CAMERA] Frame captured successfully! Size: %u bytes\n", fb->len);

  // Transmit image data via HTTP Multipart POST request
  if (WiFi.status() == WL_CONNECTED) {
    String boundary = "----ESP32Boundary" + String(millis());
    String current_server_path = String("/api/dr/") + home_id + "/rooms/" + room_id + "/telemetry";
    
    // Construct HTTP multipart body boundaries and headers
    String bodyHead = "--" + boundary + "\r\n";
    bodyHead += "Content-Disposition: form-data; name=\"image\"; filename=\"photo.jpg\"\r\n";
    bodyHead += "Content-Type: image/jpeg\r\n\r\n";
    
    String bodyTail = "\r\n--" + boundary + "--\r\n";
    uint32_t totalLen = bodyHead.length() + fb->len + bodyTail.length();
    
    WiFiClient tcpClient; 
    if (tcpClient.connect(server_ip, server_port)) {
      Serial.println("[HTTP] Transmitting multipart telemetry package to the backend server...");
      
      tcpClient.print("POST "); tcpClient.print(current_server_path); tcpClient.println(" HTTP/1.1");
      tcpClient.print("Host: "); tcpClient.println(server_ip);
      tcpClient.print("Authorization: Bearer "); tcpClient.println(jwtToken);
      tcpClient.print("Content-Length: "); tcpClient.println(totalLen);
      tcpClient.print("Content-Type: multipart/form-data; boundary="); tcpClient.println(boundary);
      tcpClient.println(); 
      
      tcpClient.print(bodyHead);
      
      // Stream the image frame buffer in structured chunks
      uint8_t *fbBuf = fb->buf;
      size_t fbLen = fb->len;
      for (size_t n = 0; n < fbLen; n = n + 1024) {
        if (n + 1024 < fbLen) {
          tcpClient.write(fbBuf, 1024);
          fbBuf += 1024;
        } else if (fbLen % 1024 > 0) {
          size_t remainder = fbLen % 1024;
          tcpClient.write(fbBuf, remainder);
        }
        // CRITICAL FIX: Keep MQTT connection alive during intensive payload transfers to prevent false LWT timeouts
        mqttClient.loop();
      }
      
      tcpClient.print(bodyTail);
      
      int timeout = 5000;
      long startTimer = millis();
      // CRITICAL FIX: Keep MQTT connection active while listening for server acknowledgment
      while (!tcpClient.available() && (millis() - startTimer < timeout)) { 
        delay(10); 
        mqttClient.loop();
      }
      
      Serial.println("[HTTP] Server response payload received:");
      while (tcpClient.available()) {
        String line = tcpClient.readStringUntil('\n');
        Serial.println(line);
      }
      tcpClient.stop();
    } else {
      Serial.println("[HTTP] Error: Unable to establish TCP socket connection with the Flask server.");
    }
  }

  // Release the camera frame buffer back to the system pool
  esp_camera_fb_return(fb); 
  Serial.println("[STATUS] Telemetry transmission complete. Resuming listener state...\n");
}

void setupCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  
  config.frame_size = FRAMESIZE_VGA; 
  config.pixel_format = PIXFORMAT_JPEG;
  config.grab_mode = CAMERA_GRAB_LATEST; 
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.jpeg_quality = 12;
  config.fb_count = 1;

  if (config.pixel_format == PIXFORMAT_JPEG) {
    if (psramFound()) {
      config.jpeg_quality = 10;
      config.fb_count = 2;
    } else {
      config.frame_size = FRAMESIZE_SVGA;
      config.fb_location = CAMERA_FB_IN_DRAM;
    }
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[CAMERA] Initialization failure with error code: 0x%x", err);
    return;
  }

  #if defined(LED_GPIO_NUM)
    ledcAttach(LED_GPIO_NUM, 5000, 8); 
  #endif
}