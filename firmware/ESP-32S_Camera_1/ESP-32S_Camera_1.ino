#include <Arduino.h>
#include "esp_camera.h"
#include <WiFi.h>
#include <WiFiClientSecure.h> 
#include <PubSubClient.h> 
#include <HTTPClient.h>
#include <ArduinoJson.h>

// ===========================
// Configurazione Hardware
// ===========================
#include "board_config.h"

// ===========================
// Credenziali Wi-Fi
// ===========================
const char *ssid = "OnePlus 8";
const char *password = "88888888";

// ===========================
// Identificativi Digital Twin
// ===========================
const char* home_id = "6a6b0e2a73e73970ad552f46"; 
const char* room_id = "507c3299-4a89-4ed5-9cdf-5bb4998b25df"; // NUOVO: Necessario per l'URL RESTful
const char* room_name = "salotto"; // Mantenuto per il login e per MQTT

// ===========================
// Configurazione MQTT (HiveMQ Cloud Privato)
// ===========================
const char* mqtt_server = "f91c2f750c5d4d2c9ff2177772a4ea75.s1.eu.hivemq.cloud"; 
const int   mqtt_port = 8883; // Porta sicura
const char* mqtt_user = "PetTracker";
const char* mqtt_password = "PetTracker26";

String topic_lwt_stato = String("casa/") + room_name + "/stato"; 
const char* mqtt_topic_trigger = "casa/porta_u1"; // Ascolta il sensore ultrasuoni

// ===========================
// Configurazione Server HTTP (Backend Flask Locale)
// ===========================
const char* server_ip = "10.101.219.100"; 
const int server_port = 5000; 
const char* server_auth_path = "/api/dr/devices/tokens"; // AGGIORNATO: Nessun verbo

// ===========================
// Variabili Globali
// ===========================
WiFiClientSecure espClient; // Usato per MQTT Criptato
PubSubClient mqttClient(espClient); 

unsigned long ultimoTentativoMQTT = 0; 
String jwt_token = ""; // Conterrà il token ottenuto dinamicamente

// Dichiarazioni funzioni
void setupCamera();
void setupWiFi();
bool loginToServer();
void reconnectMQTT();
void mqttCallback(char* topic, byte* payload, unsigned int length);
void takeAndSendPhoto();

void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(true);
  Serial.println("\nAvvio ESP32-CAM MQTT (TLS/SSL + Multipart + JWT Auth)...");

  setupCamera();
  setupWiFi();

  // Configura MQTT con la porta sicura
  mqttClient.setServer(mqtt_server, mqtt_port);
  mqttClient.setCallback(mqttCallback);
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    setupWiFi();
  }

  if (!mqttClient.connected()) {
    reconnectMQTT();
  }
  mqttClient.loop();
  
  delay(10); 
}

// =======================================================
// FUNZIONI DI SUPPORTO
// =======================================================

bool loginToServer() {
  if (WiFi.status() != WL_CONNECTED) return false;

  WiFiClient localClient; // Usiamo un client normale non criptato per il traffico locale
  HTTPClient http;
  String auth_url = String("http://") + server_ip + ":" + server_port + server_auth_path;
  
  Serial.println("[AUTH] Richiesta JWT al server locale...");
  http.begin(localClient, auth_url); 
  http.addHeader("Content-Type", "application/json");

  // Payload di autenticazione con l'identità del dispositivo
  String loginPayload = "{\"room_name\":\"" + String(room_name) + "\"}";
  
  int httpResponseCode = http.POST(loginPayload);

  if (httpResponseCode == 200) {
    String response = http.getString();
    
    StaticJsonDocument<512> doc;
    DeserializationError error = deserializeJson(doc, response);

    if (!error) {
      const char* token = doc["access_token"];
      jwt_token = String(token);
      
      Serial.println("[AUTH] Login completato! JWT ottenuto con successo.");
      http.end();
      return true;
    } else {
      Serial.println("[AUTH] Errore nel parsing del JSON di risposta.");
    }
  } else {
    Serial.printf("[AUTH] Login fallito. Codice HTTP: %d\n", httpResponseCode);
  }
  
  http.end();
  return false;
}

void setupWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  
  WiFi.begin(ssid, password);
  WiFi.setSleep(false); 

  Serial.print("Connessione al WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connesso!");
  Serial.print("Indirizzo IP: ");
  Serial.println(WiFi.localIP());

  // FONDAMENTALE PER HIVE MQ CLOUD SULLA ESP32-CAM
  espClient.setInsecure();

  // Acquisizione automatica del token JWT prima di procedere
  while (jwt_token == "") {
    loginToServer();
    if (jwt_token == "") {
      Serial.println("Ritento il login tra 5 secondi...");
      delay(5000);
    }
  }
}

void reconnectMQTT() {
  if (millis() - ultimoTentativoMQTT > 5000) {
    ultimoTentativoMQTT = millis();
    Serial.print("Tentativo di connessione ESP32-CAM a MQTT (TLS)...");
    
    String clientID = "ESP32CAM-" + String((uint32_t)ESP.getEfuseMac(), HEX);

    // Connessione con Autenticazione (User/Pass) + LWT
    if (mqttClient.connect(clientID.c_str(), mqtt_user, mqtt_password, topic_lwt_stato.c_str(), 1, true, "OFFLINE")) {
      Serial.println("Connesso al broker protetto!");
      
      // Pubblica immediatamente lo stato ONLINE (con Retain = true)
      mqttClient.publish(topic_lwt_stato.c_str(), "ONLINE", true);
      
      // Iscriviti al topic del sensore a ultrasuoni
      mqttClient.subscribe(mqtt_topic_trigger);
      Serial.printf("Iscritto al topic: %s\n", mqtt_topic_trigger);
    } else {
      Serial.print("Fallito, stato=");
      Serial.println(mqttClient.state());
    }
  }
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  Serial.printf("Messaggio ricevuto sul topic: %s\n", topic);
  
  if (String(topic) == mqtt_topic_trigger) {
    Serial.println("Rilevato movimento! Scatto foto in corso...");
    takeAndSendPhoto();
  }
}

void takeAndSendPhoto() {
  camera_fb_t * fb = NULL; 
  sensor_t * s = esp_camera_sensor_get(); 

  // --- LOGICA FLASH AUTOMATICO ---
  int aec_value = s->status.aec_value; 
  Serial.printf("Valore esposizione attuale (AEC): %d\n", aec_value);
  bool need_flash = (aec_value > 800); 

  if (need_flash) {
    Serial.println("Ambiente buio rilevato: Attivazione Flash.");
    #if defined(LED_GPIO_NUM)
      ledcWrite(LED_GPIO_NUM, 255); 
      delay(200);                   
    #endif
  }

  // SCATTO
  fb = esp_camera_fb_get(); 

  #if defined(LED_GPIO_NUM)
    ledcWrite(LED_GPIO_NUM, 0);
  #endif

  if (!fb) {
    Serial.println("Errore: Impossibile catturare l'immagine.");
    return;
  }
  Serial.printf("Foto scattata! Dimensione: %u bytes\n", fb->len);

  // --- COMPOSIZIONE MULTIPART/FORM-DATA TRAMITE TCP GREZZO ---
  if (WiFi.status() == WL_CONNECTED) {
    String boundary = "----ESP32Boundary" + String(millis());
    
    // AGGIORNATO: URL dinamico che rispetta la gerarchia REST: /api/dr/<dt_id>/rooms/<room_id>/telemetry
    String current_server_path = String("/api/dr/") + home_id + "/rooms/" + room_id + "/telemetry";
    
    // Costruzione delle intestazioni del body
    // AGGIORNATO: Rimosso il payload JSON, passiamo solo l'immagine poiché gli ID sono nell'URL
    String bodyHead = "--" + boundary + "\r\n";
    bodyHead += "Content-Disposition: form-data; name=\"image\"; filename=\"photo.jpg\"\r\n";
    bodyHead += "Content-Type: image/jpeg\r\n\r\n";
    
    String bodyTail = "\r\n--" + boundary + "--\r\n";
    uint32_t totalLen = bodyHead.length() + fb->len + bodyTail.length();
    
    WiFiClient tcpClient; // Client standard non criptato per il Server Flask in locale
    if (tcpClient.connect(server_ip, server_port)) {
      Serial.println("[HTTP] Inviando pacchetto multipart al server...");
      
      // Header HTTP con URL dinamico
      tcpClient.print("POST "); tcpClient.print(current_server_path); tcpClient.println(" HTTP/1.1");
      tcpClient.print("Host: "); tcpClient.println(server_ip);
      
      // Iniezione dinamica del token ottenuto dal login
      tcpClient.print("Authorization: Bearer "); tcpClient.println(jwt_token);
      
      tcpClient.print("Content-Length: "); tcpClient.println(totalLen);
      tcpClient.print("Content-Type: multipart/form-data; boundary="); tcpClient.println(boundary);
      tcpClient.println(); // Riga vuota che separa header dal body
      
      // Invio Intestazione multipart
      tcpClient.print(bodyHead);
      
      // Invio buffer immagine a blocchi (per evitare sovraccarichi di memoria)
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
      }
      
      // Chiusura Multipart
      tcpClient.print(bodyTail);
      
      // Lettura risposta
      int timeout = 5000;
      long startTimer = millis();
      while (!tcpClient.available() && (millis() - startTimer < timeout)) { delay(10); }
      
      Serial.println("[HTTP] Risposta del server:");
      while (tcpClient.available()) {
        String line = tcpClient.readStringUntil('\n');
        Serial.println(line);
      }
      tcpClient.stop();
    } else {
      Serial.println("[HTTP] Errore: Impossibile connettersi al server Flask.");
    }
  }

  esp_camera_fb_return(fb); 
  Serial.println("Processo completato. In attesa di nuovi trigger...\n");
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
    Serial.printf("Camera init failed with error 0x%x", err);
    return;
  }

  #if defined(LED_GPIO_NUM)
    ledcAttach(LED_GPIO_NUM, 5000, 8); 
  #endif
}