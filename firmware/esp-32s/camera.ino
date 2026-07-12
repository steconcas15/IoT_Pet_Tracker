#include <Arduino.h>
#include "esp_camera.h"
#include <WiFi.h>
#include <PubSubClient.h> // Libreria per MQTT
#include <HTTPClient.h>   // Libreria per chiamate HTTP (POST)

// ===========================
// Configurazione Hardware
// ===========================
#include "board_config.h"

// ===========================
// Credenziali Wi-Fi
// ===========================
const char *ssid = "FASTWEB-3QH6KF";
const char *password = "E2XT6XK6JG";

// ===========================
// Configurazione MQTT
// ===========================
const char* mqtt_server = "broker.mqttdashboard.com"; // INSERISCI L'IP DEL TUO BROKER MQTT (es. Mosquitto su Raspberry Pi)
const int   mqtt_port = 1883;
const char* mqtt_topic_trigger = "sensore/ultrasuoni/movimento"; // Il topic su cui "ascolta"
const char* mqtt_client_id = "ESP32_Camera_Sub";

// ===========================
// Configurazione Server HTTP (Dove inviare la foto)
// ===========================
const char* server_url = "http://192.168.1.60:8080/upload"; // L'URL (API endpoint) che riceverà l'immagine via POST

// Inizializzazione client di rete
WiFiClient espClient;
PubSubClient mqttClient(espClient);

// Dichiarazioni funzioni
void setupCamera();
void setupWiFi();
void reconnectMQTT();
void mqttCallback(char* topic, byte* payload, unsigned int length);
void takeAndSendPhoto();

void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(true);
  Serial.println("\nAvvio ESP32-CAM MQTT...");

  setupCamera();
  setupWiFi();

  // Configura MQTT
  mqttClient.setServer(mqtt_server, mqtt_port);
  mqttClient.setCallback(mqttCallback);
}

void loop() {
  // Mantieni la connessione MQTT viva
  if (!mqttClient.connected()) {
    reconnectMQTT();
  }
  mqttClient.loop();

  // Qui non facciamo nulla, aspettiamo che arrivi un messaggio MQTT
  // che attiverà la funzione mqttCallback()
  delay(10); 
}

// =======================================================
// FUNZIONI DI SUPPORTO
// =======================================================

void setupWiFi() {
  WiFi.begin(ssid, password);
  WiFi.setSleep(false); // Importante per non perdere messaggi MQTT

  Serial.print("Connessione al WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connesso!");
  Serial.print("Indirizzo IP: ");
  Serial.println(WiFi.localIP());
}

void reconnectMQTT() {
  // Loop finché non ci riconnettiamo
  while (!mqttClient.connected()) {
    Serial.print("Tentativo di connessione MQTT...");
    
    // Tenta la connessione (Aggiungi utente/password qui se il tuo broker li richiede: mqttClient.connect(mqtt_client_id, "user", "pass"))
    if (mqttClient.connect(mqtt_client_id)) {
      Serial.println("Connesso al broker MQTT!");
      
      // Iscriviti al topic del sensore a ultrasuoni
      mqttClient.subscribe(mqtt_topic_trigger);
      Serial.printf("Iscritto al topic: %s\n", mqtt_topic_trigger);
    } else {
      Serial.print("Fallito, stato=");
      Serial.print(mqttClient.state());
      Serial.println(" Riprovo tra 5 secondi");
      delay(5000);
    }
  }
}

// Funzione richiamata ogni volta che arriva un messaggio sul topic a cui siamo iscritti
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  Serial.printf("Messaggio ricevuto sul topic: %s\n", topic);
  
  // Convertiamo il payload in stringa (opzionale, ma utile per debug)
  String message;
  for (int i = 0; i < length; i++) {
    message += (char)payload[i];
  }
  Serial.print("Contenuto: ");
  Serial.println(message);

  // Se il topic corrisponde a quello del sensore, scattiamo la foto
  if (String(topic) == mqtt_topic_trigger) {
    // Spesso il sensore manda messaggi come "ON", "1", o "MOTION". 
    // Puoi aggiungere un if (message == "1") se vuoi filtrare, 
    // ma qui assumiamo che QUALSIASI messaggio su questo topic sia un trigger.
    Serial.println("Rilevato movimento! Scatto foto in corso...");
    takeAndSendPhoto();
  }
}

void takeAndSendPhoto() {
  // 1. Scatta la foto
  camera_fb_t * fb = NULL;
  sensor_t * s = esp_camera_sensor_get(); // Otteniamo il puntatore al sensore per leggere i parametri

  // --- LOGICA FLASH AUTOMATICO ---
  // Leggiamo il valore di esposizione attuale (AEC).
  // Se la scena è buia, il sensore alza questo valore per compensare.
  int aec_value = s->status.aec_value;
  Serial.printf("Valore esposizione attuale (AEC): %d\n", aec_value);

  // Soglia di luminosità: se aec_value > 800, la scena è considerata buia.
  // Regola questo valore (es. tra 500 e 1000) dopo qualche test al buio.
  bool need_flash = (aec_value > 800); 

  if (need_flash) {
    Serial.println("Ambiente buio rilevato: Attivazione Flash.");
    #if defined(LED_GPIO_NUM)
      ledcWrite(LED_GPIO_NUM, 255); // Flash al massimo della potenza
      delay(200);                   // Tempo necessario affinché la luce illumini la scena
    #endif
  }
  // -------------------------------

  fb = esp_camera_fb_get(); // SCATTO!

  // Spegni subito il Flash dopo lo scatto
  #if defined(LED_GPIO_NUM)
    ledcWrite(LED_GPIO_NUM, 0);
  #endif

  if (!fb) {
    Serial.println("Errore: Impossibile catturare l'immagine.");
    return;
  }
  Serial.printf("Foto scattata! Dimensione: %u bytes\n", fb->len);

  // 2. Prepara e invia la richiesta HTTP POST
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    
    Serial.print("Invio POST a: ");
    Serial.println(server_url);
    
    http.begin(espClient, server_url);
    
    // Imposta gli header HTTP corretti per inviare un file binario puro (l'immagine JPEG)
    http.addHeader("Content-Type", "image/jpeg");
    // Opzionale: aggiungi un header personalizzato per indicare il dispositivo
    http.addHeader("X-Device", "ESP32-CAM-1"); 

    // Esegui la POST inviando direttamente il buffer della memoria della fotocamera
    int httpResponseCode = http.POST(fb->buf, fb->len);

    if (httpResponseCode > 0) {
      Serial.printf("HTTP Response code: %d\n", httpResponseCode);
      String response = http.getString();
      Serial.println("Risposta del server: " + response);
    } else {
      Serial.printf("Codice errore HTTP: %d\n", httpResponseCode);
      Serial.println(http.errorToString(httpResponseCode).c_str());
    }
    
    http.end(); // Libera le risorse HTTP
  } else {
    Serial.println("Errore: WiFi non connesso. Impossibile inviare la foto.");
  }

  // 3. IMPORTANTISSIMO: Libera la memoria della fotocamera
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
  
  // Impostiamo una risoluzione ragionevole (SVGA 800x600 o VGA 640x480) per 
  // non inviare file enormi (UXGA) via rete al server HTTP.
  config.frame_size = FRAMESIZE_VGA; 
  config.pixel_format = PIXFORMAT_JPEG;
  config.grab_mode = CAMERA_GRAB_LATEST; // Vogliamo la foto più recente
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

  // camera init
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed with error 0x%x", err);
    return;
  }

  // Setup LED Flash pin
  #if defined(LED_GPIO_NUM)
    ledcAttach(LED_GPIO_NUM, 5000, 8); // Setup PWM per il flash
  #endif
}
