#include "SensorHub.hpp"

#include <Wire.h>
#include <DHT.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <Adafruit_BMP280.h>

// ---------------- Configuration ----------------
static const unsigned long DEFAULT_SAMPLE_MS = 1000;
static const unsigned long HEARTBEAT_MS      = 5000;

static const uint8_t PIN_DHT        = 2;  // DHT11/DHT22 data
static const uint8_t PIN_ONEWIRE    = 3;  // DS18B20 data
static const uint8_t PIN_HCSR04_TRG = 4;  // HC-SR04 trigger
static const uint8_t PIN_HCSR04_ECH = 5;  // HC-SR04 echo
static const uint8_t PIN_PIR        = 6;  // PIR motion sensor data

static const uint8_t ANALOG_PINS[]  = {A0, A1, A2, A3};
static const size_t  ANALOG_COUNT   = sizeof(ANALOG_PINS) / sizeof(ANALOG_PINS[0]);

#define DHT_TYPE DHT22

// ---------------- Globals ----------------
static DHT dht(PIN_DHT, DHT_TYPE);
static OneWire oneWire(PIN_ONEWIRE);
static DallasTemperature ds18b20(&oneWire);
static Adafruit_BMP280 bmp; // I2C

static bool haveDHT       = false;
static bool haveDS18B20   = false;
static bool haveBMP280    = false;
static bool haveUltrasonic= false;
static bool haveAnalog[ANALOG_COUNT];

static bool streamingEnabled = true;
static unsigned long sampleIntervalMs = DEFAULT_SAMPLE_MS;
static unsigned long tLastSample = 0;
static unsigned long tLastHeartbeat = 0;

static String cmdBuf;

// ---------------- JSON Helpers ----------------
static void jsonKV_str(const char* key, const char* val) {
    Serial.print('"'); Serial.print(key); Serial.print("\":\"");
    Serial.print(val); Serial.print('"');
}
static void jsonKV_num(const char* key, float val) {
    Serial.print('"'); Serial.print(key); Serial.print("\":");
    Serial.print(val, 6);
}
static void jsonKV_int(const char* key, long val) {
    Serial.print('"'); Serial.print(key); Serial.print("\":");
    Serial.print(val);
}

static void sendMessage(const char* type, const char* payloadKey = nullptr, const char* payloadVal = nullptr) {
    Serial.print('{');
    jsonKV_str("type", type);
    Serial.print(',');
    jsonKV_int("ts", millis());
    if (payloadKey && payloadVal) {
        Serial.print(',');
        jsonKV_str(payloadKey, payloadVal);
    }
    Serial.println('}');
}

static void sendError(const char* msg) {
    Serial.print('{');
    jsonKV_str("type", "ERROR"); Serial.print(',');
    jsonKV_int("ts", millis());  Serial.print(',');
    jsonKV_str("message", msg);
    Serial.println('}');
}

static void sendLog(const char* msg) {
    Serial.print('{');
    jsonKV_str("type", "LOG"); Serial.print(',');
    jsonKV_int("ts", millis()); Serial.print(',');
    jsonKV_str("message", msg);
    Serial.println('}');
}

// ---------------- Detection ----------------
static void detectDHT() {
    dht.begin();
    delay(100);
    float t = dht.readTemperature();
    float h = dht.readHumidity();
    haveDHT = !(isnan(t) && isnan(h));
}
static void detectDS18B20() {
    ds18b20.begin();
    delay(50);
    oneWire.reset_search();
    byte addr[8];
    haveDS18B20 = oneWire.search(addr);
    oneWire.reset_search();
}
static void detectBMP280() {
    haveBMP280 = bmp.begin(0x76) || bmp.begin(0x77);
}
static void detectUltrasonic() {
    pinMode(PIN_HCSR04_TRG, OUTPUT);
    pinMode(PIN_HCSR04_ECH, INPUT);
    digitalWrite(PIN_HCSR04_TRG, LOW); delayMicroseconds(2);
    digitalWrite(PIN_HCSR04_TRG, HIGH); delayMicroseconds(10);
    digitalWrite(PIN_HCSR04_TRG, LOW);
    unsigned long dur = pulseIn(PIN_HCSR04_ECH, HIGH, 30000UL);
    haveUltrasonic = dur > 0;
}
static void detectAnalog() {
    for (size_t i = 0; i < ANALOG_COUNT; ++i) {
        pinMode(ANALOG_PINS[i], INPUT);
        int v = analogRead(ANALOG_PINS[i]);
        haveAnalog[i] = (v > 0);
    }
}
static void detectPIR() {
    pinMode(PIN_PIR, INPUT);
    // A simple check: if the pin isn't always LOW, assume it's connected
    // This is a basic detection, a real world scenario might involve more complex checks
    int val = digitalRead(PIN_PIR);
    havePIR = (val == HIGH || val == LOW); // If we can read it, it's there
}
static void detectAll() {
    detectDHT(); detectDS18B20(); detectBMP280();
    detectUltrasonic(); detectAnalog(); detectPIR();
}

// ---------------- Inventory ----------------
static void sendInventory() {
    Serial.print('{');
    jsonKV_str("type", "INVENTORY"); Serial.print(',');
    jsonKV_int("ts", millis()); Serial.print(',');
    Serial.print("\"sensors\":{");

    bool first = true;

    if (haveDHT) {
        if (!first) Serial.print(','); first = false;
        Serial.print("\"DHT\":{"); jsonKV_str("model", DHT_TYPE == DHT22 ? "DHT22" : "DHT11"); Serial.print('}');
    }
    if (haveDS18B20) {
        if (!first) Serial.print(','); first = false;
        Serial.print("\"DS18B20\":{"); jsonKV_str("bus", "OneWire"); Serial.print('}');
    }
    if (haveBMP280) {
        if (!first) Serial.print(','); first = false;
        Serial.print("\"BMP280\":{"); jsonKV_str("bus", "I2C"); Serial.print('}');
    }
    if (haveUltrasonic) {
        if (!first) Serial.print(','); first = false;
        Serial.print("\"HC_SR04\":{"); jsonKV_str("pins", "TRIG:D4,ECHO:D5"); Serial.print('}');
    }
    if (havePIR) {
        if (!first) Serial.print(','); first = false;
        Serial.print("\"PIR\":{"); jsonKV_str("pin", String(PIN_PIR).c_str()); Serial.print('}');
    }
    bool anyAnalog = false;
    for (size_t i = 0; i < ANALOG_COUNT; ++i) if (haveAnalog[i]) { anyAnalog = true; break; }
    if (anyAnalog) {
        if (!first) Serial.print(','); first = false;
        Serial.print("\"ANALOG\":{");
        Serial.print("\"channels\":[");
        bool f2 = true;
        for (size_t i = 0; i < ANALOG_COUNT; ++i) {
            if (!haveAnalog[i]) continue;
            if (!f2) Serial.print(',');
            Serial.print('"'); Serial.print((int)ANALOG_PINS[i]); Serial.print('"');
            f2 = false;
        }
        Serial.print("]}");
    }

    Serial.print("}}");
    Serial.println();
}

// ---------------- Sampling ----------------
static void sampleDHT() {
    float t = dht.readTemperature();
    float h = dht.readHumidity();
    Serial.print('{'); jsonKV_str("type", "DATA"); Serial.print(',');
    jsonKV_int("ts", millis()); Serial.print(',');
    jsonKV_str("sensor", "DHT"); Serial.print(',');
    Serial.print("\"values\":{");
    bool first = true;
    if (!isnan(t)) { if (!first) Serial.print(','); first = false; jsonKV_num("temperature_c", t); }
    if (!isnan(h)) { if (!first) Serial.print(','); first = false; jsonKV_num("humidity_pct", h); }
    Serial.print("}}"); Serial.println();
}
static void sampleDS18B20() {
    ds18b20.requestTemperatures();
    float tempC = ds18b20.getTempCByIndex(0);
    Serial.print('{'); jsonKV_str("type", "DATA"); Serial.print(',');
    jsonKV_int("ts", millis()); Serial.print(',');
    jsonKV_str("sensor", "DS18B20"); Serial.print(',');
    Serial.print("\"values\":{"); jsonKV_num("temperature_c", tempC); Serial.print("}}"); Serial.println();
}
static void sampleBMP280() {
    float t = bmp.readTemperature();
    float p = bmp.readPressure();
    float a = bmp.readAltitude(1013.25);
    Serial.print('{'); jsonKV_str("type", "DATA"); Serial.print(',');
    jsonKV_int("ts", millis()); Serial.print(',');
    jsonKV_str("sensor", "BMP280"); Serial.print(',');
    Serial.print("\"values\":{");
    bool first = true;
    if (!isnan(t)) { if (!first) Serial.print(','); first = false; jsonKV_num("temperature_c", t); }
    if (!isnan(p)) { if (!first) Serial.print(','); first = false; jsonKV_num("pressure_pa", p); }
    if (!isnan(a)) { if (!first) Serial.print(','); first = false; jsonKV_num("altitude_m", a); }
    Serial.print("}}"); Serial.println();
}
static void sampleUltrasonic() {
    digitalWrite(PIN_HCSR04_TRG, LOW); delayMicroseconds(2);
    digitalWrite(PIN_HCSR04_TRG, HIGH); delayMicroseconds(10);
    digitalWrite(PIN_HCSR04_TRG, LOW);
    unsigned long dur = pulseIn(PIN_HCSR04_ECH, HIGH, 30000UL);
    float distanceCm = (dur / 2.0f) * 0.0343f;
    Serial.print('{'); jsonKV_str("type", "DATA"); Serial.print(',');
    jsonKV_int("ts", millis()); Serial.print(',');
    jsonKV_str("sensor", "HC_SR04"); Serial.print(',');
    Serial.print("\"values\":{"); jsonKV_num("distance_cm", distanceCm); Serial.print("}}"); Serial.println();
}
static void samplePIR() {
    int motionDetected = digitalRead(PIN_PIR);
    Serial.print('{'); jsonKV_str("type", "DATA"); Serial.print(',');
    jsonKV_int("ts", millis()); Serial.print(',');
    jsonKV_str("sensor", "PIR"); Serial.print(',');
    Serial.print("\"values\":{"); jsonKV_int("motion", motionDetected); Serial.print("}}"); Serial.println();
}
static void sampleAnalog() {
    for (size_t i = 0; i < ANALOG_COUNT; ++i) {
        if (!haveAnalog[i]) continue;
        int raw = analogRead(ANALOG_PINS[i]);
        Serial.print('{'); jsonKV_str("type", "DATA"); Serial.print(',');
        jsonKV_int("ts", millis()); Serial.print(',');
        jsonKV_str("sensor", "ANALOG"); Serial.print(',');
        Serial.print("\"values\":{");
        jsonKV_int("pin", ANALOG_PINS[i]); Serial.print(',');
        jsonKV_int("raw", raw); Serial.print("}}"); Serial.println();
    }
}
static void sendHeartbeat() {
    Serial.print('{');
    jsonKV_str("type", "HEARTBEAT"); Serial.print(',');
    jsonKV_int("ts", millis()); Serial.print(',');
    jsonKV_int("interval_ms", sampleIntervalMs); Serial.print(',');
    jsonKV_str("mode", streamingEnabled ? "STREAMING" : "PAUSED");
    Serial.print('}'); Serial.println();
}

// ---------------- Commands ----------------
static void processCommand(const String& cmdLine) {
    String cmd = cmdLine; cmd.trim(); cmd.toUpperCase();
    if (cmd.length() == 0) return;
    if (cmd == "PING") {
        sendMessage("LOG", "message", "PONG");
    } else if (cmd == "INVENTORY") {
        sendInventory();
    } else if (cmd == "START") {
        streamingEnabled = true; sendLog("Streaming enabled");
    } else if (cmd == "STOP") {
        streamingEnabled = false; sendLog("Streaming paused");
    } else if (cmd.startsWith("SET_RATE")) {
        int idx = cmd.indexOf(' ');
        if (idx > 0) {
            unsigned long v = cmd.substring(idx + 1).toInt();
            if (v >= 100) { sampleIntervalMs = v; sendLog("Sample rate updated"); }
            else { sendError("SET_RATE too low (min 100 ms)"); }
        } else sendError("SET_RATE requires value");
    } else if (cmd == "STATUS") {
        sendInventory(); sendHeartbeat();
    } else if (cmd == "RESET") {
        sendLog("Resetting..."); delay(100); asm volatile ("jmp 0");
    } else sendError("Unknown command");
}
static void pollSerial() {
    while (Serial.available()) {
        char c = (char)Serial.read();
        if (c == '\n' || c == '\r') {
            if (cmdBuf.length() > 0) { processCommand(cmdBuf); cmdBuf = ""; }
        } else {
            if (cmdBuf.length() < 120) { cmdBuf += c; }
        }
    }
}

// ---------------- Public API ----------------
void SensorHub::begin(unsigned long baudrate) {
    Serial.begin(baudrate);
    while (!Serial) {}
    sendLog("Booting Sensor Hub...");
    detectAll(); sendInventory(); sendHeartbeat();
    tLastSample = millis(); tLastHeartbeat = millis();
}

void SensorHub::update() {
    unsigned long now = millis();
    pollSerial();
    if (now - tLastHeartbeat >= HEARTBEAT_MS) {
        sendHeartbeat(); tLastHeartbeat = now;
    }
    if (!streamingEnabled) return;
    if (now - tLastSample >= sampleIntervalMs) {
        if (haveDHT)        sampleDHT();
        if (haveDS18B20)    sampleDS18B20();
        if (haveBMP280)     sampleBMP280();
        if (haveUltrasonic) sampleUltrasonic();
        if (havePIR)        samplePIR();
        sampleAnalog();
        tLastSample = now;
    }
}
