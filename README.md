# 📚 Fingerprint-Based Attendance System using ESP32 and Flask

This project integrates an ESP32 microcontroller with a fingerprint sensor and a Flask-based web server to build a smart attendance system. The ESP32 scans fingerprints, identifies users, and sends their data to the Flask API. The server logs attendance and associates it with specific subjects.

---

## 🔧 Features

- 🔐 Fingerprint authentication via Adafruit Fingerprint Sensor
- 📶 ESP32 with static IP Wi-Fi configuration
- 🌐 REST API built using Flask (Python)
- 📤 ESP32 sends authenticated fingerprint ID and subject ID to Flask
- 🧠 Subject-based attendance logging
- 🛠 Web server endpoint to trigger scan start/stop and set subject
- 📊 Attendance tracking via MySQL or file-based logging

---

## ⚙️ Requirements

Hardware
- ESP32 board (e.g., NodeMCU-32S)
- Adafruit R305 or similar fingerprint sensor
- Breadboard and jumper wires
- Wi-Fi network

Software
- Arduino IDE with:
- Adafruit Fingerprint Sensor Library
- rduinoJson
- Python 3.x with Flask
- MySQL (optional, if logging to database)
- OS: Windows

---

## 📥 Clone the Project and Run Server

1. Open your terminal then run this:
    -> git clone https://github.com/law4percent/attendance-system-chloe-danag.git
    -> cd fingerprint-attendance-system

2. Create a virtualenv (recommended). Run this:
    -> pip install virtualenv
    -> py -m venv venv
    -> venv\Scripts\activate.bat

3. Install dependencies: 
    -> pip install -r requirements.txt

4. Run the server: 
    -> python app.py
---

## 💻 ESP32 Firmware
1. Open fingerprint_main.ino in Arduino IDE.

2. Set your wifi_credentials.h with:
    #define SSID "your_wifi_name"
    #define PASSWORD "your_wifi_password"
    #define IPv4 "192.168.1.100" // IP of your Flask server

3. Upload the sketch to the ESP32.