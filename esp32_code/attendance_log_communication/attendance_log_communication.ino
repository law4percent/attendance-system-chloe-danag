#include <Adafruit_Fingerprint.h>
#include <HardwareSerial.h>
#include <ArduinoJson.h>
#include <SPI.h>
#include <MFRC522.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

#include "Credentials.h"

#define SS_PIN 5   // RFID SDA pin
#define RST_PIN 4  // RFID RST pin

#define LED_RED 13
#define LED_GREEN 12
long isOn = 1;

// RFID
MFRC522 rfid(SS_PIN, RST_PIN);

// LCD - 20 columns, 4 rows (adjust address if needed)
LiquidCrystal_I2C lcd(0x27, 20, 4);

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

  pinMode(LED_RED, OUTPUT);
  pinMode(LED_GREEN, OUTPUT);

  digitalWrite(LED_GREEN, LOW);
  digitalWrite(LED_RED, HIGH);

  SPI.begin();
  rfid.PCD_Init();

  // LCD setup
  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print("  RFID Access Sys  ");
  lcd.setCursor(0, 1);
  lcd.print(" Scan your card... ");
}

void loop() {
  // === RFID SCAN ===
  if (rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
    String rfidUID = getHexUID(rfid.uid.uidByte, rfid.uid.size);

    Serial.print("RFID UID: ");
    Serial.println(rfidUID);

    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("Card Detected:");
    lcd.setCursor(0, 1);
    lcd.print(rfidUID);

    int isMatch = searchToMatch(rfidUID, SIZE_OF_REGISTERED_RFID);

    if (isMatch == 1) {
      digitalWrite(LED_GREEN, HIGH);
      digitalWrite(LED_RED, LOW);
      lcd.setCursor(0, 2);
      lcd.print(" ACCESS GRANTED ✅ ");  // DOOR UNLOCKED
      lcd.setCursor(0, 3);
      lcd.print("    DOOR UNLOCKED   ");
    } else if (isMatch == 0) {
      digitalWrite(LED_GREEN, LOW);
      digitalWrite(LED_RED, HIGH);
      lcd.setCursor(0, 2);
      lcd.print("  ACCESS DENIED ❌  ");  // DOOR LOCKED
      lcd.setCursor(0, 3);
      lcd.print("     DOOR LOCKED    ");
    } else {
      Serial.println("The scanned RFID was unregistered! ⚠️");
      lcd.setCursor(0, 2);
      lcd.print(" Unregistered Card ");
      lcd.setCursor(0, 3);
      lcd.print("  PLEASE CONTACT IT ");
    }

    delay(3000);
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("  RFID Access Sys  ");
    lcd.setCursor(0, 1);
    lcd.print(" Scan your card... ");

    rfid.PICC_HaltA();
    rfid.PCD_StopCrypto1();
  }

  // === PC Trigger Listening ===
  int received_subject = waitingForToTrigger();
  if (received_subject != 0) {
    subject_id = received_subject;
    Serial.println("Start command received for subject " + String(subject_id));
  }

  if (subject_id == 0) {
    delay(500);
    return;
  }

  // === FINGERPRINT SCAN ===
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("  Place your finger ");
  lcd.setCursor(0, 1);
  lcd.print("   for scanning...  ");

  int p = getFingerprintIDez();
  if (p != -1) {
    Serial.println("Fingerprint ID: " + String(p));
    lcd.setCursor(0, 2);
    lcd.print("  MATCH FOUND ✅ ID:");
    lcd.setCursor(17, 2);
    lcd.print(p);
    lcd.setCursor(0, 3);
    lcd.print("Sending data to PC..");

    sendFingerprintToPC(p, subject_id);
    delay(2000);
  } else {
    Serial.println("Fingerprint not found");
    lcd.setCursor(0, 2);
    lcd.print(" NO MATCH FOUND ❌ ");
    lcd.setCursor(0, 3);
    lcd.print(" Try again slowly.. ");
    delay(2000);
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


String getHexUID(byte* buffer, byte bufferSize) {
  String uidString = "";
  for (byte i = 0; i < bufferSize; i++) {
    if (buffer[i] < 0x10) uidString += "0";
    uidString += String(buffer[i], HEX);
  }
  uidString.toUpperCase();
  return uidString;
}

int searchToMatch(String get_rfid, int size) {
  for (int i = 0; i != size; i++) {
    if (get_rfid == registered_RFID[i]) {
      isOn++;
      return isOn % 2 == 0;
    }
  }
  return -1;
}