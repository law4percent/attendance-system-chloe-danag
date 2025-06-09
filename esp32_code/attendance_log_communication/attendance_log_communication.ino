#include <Adafruit_Fingerprint.h>
#include <HardwareSerial.h>
#include <ArduinoJson.h>

// Use UART2 for fingerprint sensor (GPIO16=RX, GPIO17=TX)
HardwareSerial mySerial(1);  // Use UART1 on ESP32
Adafruit_Fingerprint finger = Adafruit_Fingerprint(&mySerial);

// Global variables
int subject_id = 0;
String command = "";

void setup() {
  Serial.begin(115200);  // USB Serial to PC
  mySerial.begin(57600, SERIAL_8N1, 16, 17);  // RX=16, TX=17
  checkFingerprint();
}

void loop() {
  // Listen for subject_id trigger from PC
  int received_subject = waitingForToTrigger();
  if (received_subject != 0) {
    subject_id = received_subject;
    Serial.println("Start command received for subject " + String(subject_id));
  }

  if (subject_id == 0) {
    delay(500);
    return;
  }

  // Fingerprint process
  int p = getFingerprintIDez();
  if (p != -1) {
    sendFingerprintToPC(p, subject_id);
    delay(2000);  // Prevent repeated detection
  } else {
    Serial.println("Fingerprint not found");
  }

  delay(1000);
}


// returns -1 if failed, otherwise returns ID #
int getFingerprintIDez() {
  uint8_t p = finger.getImage();
  if (p != FINGERPRINT_OK)  return -1;

  p = finger.image2Tz();
  if (p != FINGERPRINT_OK)  return -1;

  p = finger.fingerFastSearch();
  if (p != FINGERPRINT_OK)  return -1;

  // found a match!
  Serial.print("Found ID #"); Serial.print(finger.fingerID);
  Serial.print(" with confidence of "); Serial.println(finger.confidence);
  return finger.fingerID;
}



int waitingForToTrigger() {
  if (Serial.available()) {
    command = Serial.readStringUntil('\n');
    if (command.endsWith("-start")) {
      int parsed_id = command.substring(0, command.indexOf("-")).toInt();
      return parsed_id;
    }
    
    if (command.endsWith("-stop")) {
      int parsed_id = command.substring(0, command.indexOf("-")).toInt();
      return parsed_id;
    }
  }
  return 0;
}

void sendFingerprintToPC(int fingerprint_id, int subject_id) {
  String jsonData = "{\"fingerprint_id\": " + String(fingerprint_id) + ", \"subject_id\": " + String(subject_id) + "}";
  Serial.println(jsonData);  // Send JSON over USB serial
}

void checkFingerprint() {
  delay(5);
  if (finger.verifyPassword()) {
    Serial.println("Found fingerprint sensor!");
  } else {
    Serial.println("Did not find fingerprint sensor :(");
    while (1) { delay(1); }
  }

  Serial.println(F("Reading sensor parameters"));
  finger.getParameters();
  Serial.print(F("Status: 0x")); Serial.println(finger.status_reg, HEX);
  Serial.print(F("Sys ID: 0x")); Serial.println(finger.system_id, HEX);
  Serial.print(F("Capacity: ")); Serial.println(finger.capacity);
  Serial.print(F("Security level: ")); Serial.println(finger.security_level);
  Serial.print(F("Device address: ")); Serial.println(finger.device_addr, HEX);
  Serial.print(F("Packet len: ")); Serial.println(finger.packet_len);
  Serial.print(F("Baud rate: ")); Serial.println(finger.baud_rate);

  finger.getTemplateCount();

  if (finger.templateCount == 0) {
    Serial.print("Sensor doesn't contain any fingerprint data. Please run the 'enroll' example.");
  }
  else {
    Serial.println("Waiting for valid finger...");
      Serial.print("Sensor contains "); Serial.print(finger.templateCount); Serial.println(" templates");
  }
}
