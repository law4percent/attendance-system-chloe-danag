#include <WiFi.h>
#include <HTTPClient.h>
#include <Adafruit_Fingerprint.h>
#include <HardwareSerial.h>
#include <WebServer.h>
#include <ArduinoJson.h>

#include "wifi_credentials.h"

// Replace with your WiFi credentials
const char* ssid = SSID;
const char* password = PASSWORD;

IPAddress local_IP(192, 168, 1, 200);      // Desired static IP
IPAddress gateway(192, 168, 1, 1);         // Typically your router's IP
IPAddress subnet(255, 255, 255, 0);        // Subnet mask
IPAddress primaryDNS(8, 8, 8, 8);          // Optional
IPAddress secondaryDNS(8, 8, 4, 4);        // Optional

// Flask API endpoint
const char* flaskURL = "http://" + String(IPv4) + ":5000/api/fingerprint_log";

// Subject ID (will be set via request)
int subject_id = -1;
bool isScanning = false;
WebServer server(5000);

// Use UART2 for fingerprint sensor (GPIO16=RX, GPIO17=TX)
HardwareSerial fpSerial(2);
Adafruit_Fingerprint finger = Adafruit_Fingerprint(&fpSerial);

void setup() {
  Serial.begin(115200);
  fpSerial.begin(57600, SERIAL_8N1, 16, 17);  // RX, TX for fingerprint

  connectToWiFi();
  onServer();
  server.begin();

  checkFingerprint();
  checkFingerprintTemplate();
}

void loop() {
  server.handleClient();

  if (!isScanning || subject_id == -1) {
    delay(500);
    return;
  }

  uint8_t p = finger.getImage();
  if (p != FINGERPRINT_OK) {
    delay(500);
    return;
  }

  p = finger.image2Tz();
  if (p != FINGERPRINT_OK) {
    delay(500);
    return;
  }

  p = finger.fingerFastSearch();
  if (p == FINGERPRINT_OK) {
    Serial.print(">>> Found fingerprint ID #");
    Serial.println(finger.fingerID);
    sendFingerprintToFlask(finger.fingerID, subject_id);
    delay(2000);  // Prevent duplicate scans
  } else {
    Serial.println("Fingerprint not found");
  }

  delay(1000);
}


void connectToWiFi() {
  Serial.print("Connecting to ");
  Serial.println(ssid);

  // Configure static IP
  if (!WiFi.config(local_IP, gateway, subnet, primaryDNS, secondaryDNS)) {
    Serial.println("❌ Failed to configure static IP");
  }

  WiFi.begin(ssid, password);

  int attempt = 0;
  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    Serial.print(".");
    attempt++;
    if (attempt > 20) {
      Serial.println("❌ Failed to connect to WiFi");
      return;
    }
  }

  Serial.println("\n✅ WiFi connected!");
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());
}

bool reconnectToWiFi() {
  Serial.println("WiFi not connected. Attempting to reconnect...");
  WiFi.begin(ssid, password);

  unsigned long startAttemptTime = millis();
  const unsigned long timeout = 10000;  // 10 seconds

  while (WiFi.status() != WL_CONNECTED && millis() - startAttemptTime < timeout) {
    delay(500);
    Serial.print(".");
  }

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("\nFailed to reconnect to WiFi. ❌");
    return 0;
  } else {
    Serial.println("\nReconnected to WiFi. ✅");
    return 1;
  }
}

void sendFingerprintToFlask(int fingerprint_id, int subject_id) {
  if (WiFi.status() != WL_CONNECTED) {
    if (!reconnectToWiFi()) return;
  }

  HTTPClient http;
  http.begin(flaskURL);
  http.addHeader("Content-Type", "application/json");

  String postData = "{\"fingerprint_id\": " + String(fingerprint_id) + ", \"subject_id\": " + String(subject_id) + "}";
  int httpResponseCode = http.POST(postData);

  if (httpResponseCode > 0) {
    String response = http.getString();
    Serial.println("Response: " + response);
  } else {
    Serial.println("Error on sending POST");
  }

  http.end();
}

void checkFingerprint() {
  if (finger.begin()) {
    Serial.println("Fingerprint sensor detected... ✅");
  } else {
    Serial.println("Could not find fingerprint sensor 😥");
    while (1) delay(1);
  }
}

void checkFingerprintTemplate() {
  finger.getTemplateCount();
  Serial.print("Sensor contains ");
  Serial.print(finger.templateCount);
  Serial.println(" templates");
}

void onServer() {
  server.on("/set_subject", HTTP_POST, []() {
    if (server.hasArg("plain")) {
      String body = server.arg("plain");
      DynamicJsonDocument doc(1024);
      DeserializationError error = deserializeJson(doc, body);

      if (error) {
        Serial.println("Failed to parse JSON");
        server.send(400, "application/json", "{\"error\": \"Invalid JSON\"}");
        return;
      }

      if (doc.containsKey("subject_id") && doc.containsKey("status")) {
        subject_id = doc["subject_id"];
        String status = doc["status"];
        isScanning = (status == "start");

        Serial.print("Received subject_id: ");
        Serial.println(subject_id);
        Serial.print("Scanning status: ");
        Serial.println(isScanning ? "STARTED" : "STOPPED");

        server.send(200, "application/json", "{\"status\": \"subject_id and scan status updated\"}");
      } else {
        server.send(400, "application/json", "{\"error\": \"Missing subject_id or status\"}");
      }
    } else {
      server.send(400, "application/json", "{\"error\": \"No data received\"}");
    }
  });

  // Add GET /status route for debugging
  server.on("/status", HTTP_GET, []() {
    String response = "{";
    response += "\"subject_id\": " + String(subject_id) + ",";
    response += "\"isScanning\": " + String(isScanning ? "true" : "false");
    response += "}";
    server.send(200, "application/json", response);
  });
}

