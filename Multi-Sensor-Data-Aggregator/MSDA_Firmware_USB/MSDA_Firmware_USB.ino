/*
 * MSDA_Firmware_USB.ino — Issue #1 version: Serial (USB for testing)
 * Protocol: <TYPE|TIMESTAMP_MS|CONTENT>
 *
 * Use this for:
 *   - Laptop testing (COM9 on Windows)
 *   - Raspberry Pi USB testing (/dev/ttyACM0)
 *
 * For Pi GPIO (Issue #2), use MSDA_Firmware.ino (Serial1 version).
 *
 * HC-SR04: TRIG → D4, ECHO → D5
 */

#include <DHT.h>

#define PIN_TRIG  4
#define PIN_ECHO  5
#define PIN_PIR   12
#define PIN_DHT   14
#define DHTTYPE   DHT11

DHT dht(PIN_DHT, DHTTYPE);

unsigned long sampleIntervalMs = 2000;
unsigned long heartbeatMs      = 5000;
unsigned long tLastSample      = 0;
unsigned long tLastHeartbeat   = 0;

String cmdBuf = "";

// ── Protocol helpers ──────────────────────────────────────────────
void sendMsg(const char* type, const char* content) {
  Serial.print('<'); Serial.print(type); Serial.print('|');
  Serial.print(millis()); Serial.print('|');
  Serial.print(content); Serial.println('>');
}

void sendHeartbeat() { sendMsg("HEARTBEAT", "OK"); }

void sendInventory() {
  Serial.print("<INVENTORY|"); Serial.print(millis());
  Serial.print("|3|HC_SR04:distance,DHT11:temperature:humidity,PIR:motion>");
  Serial.println();
}

// ── HC-SR04 sampling ─────────────────────────────────────────────
void sampleHCSR04() {
  digitalWrite(PIN_TRIG, LOW);  delayMicroseconds(5);
  digitalWrite(PIN_TRIG, HIGH); delayMicroseconds(15);
  digitalWrite(PIN_TRIG, LOW);

  unsigned long dur = pulseIn(PIN_ECHO, HIGH, 60000UL);
  float distCm = dur * 0.01715f;

  Serial.print("<DATA|"); Serial.print(millis());
  Serial.print("|HC_SR04,"); Serial.print(distCm, 2);
  Serial.print(",raw_us="); Serial.print(dur);
  Serial.println('>');
}

// ── DHT11 sampling ───────────────────────────────────────────────
void sampleDHT() {
  float h = dht.readHumidity();
  float t = dht.readTemperature();

  Serial.print("<DATA|"); Serial.print(millis());
  Serial.print("|DHT11,");
  
  if (isnan(h) || isnan(t)) {
    Serial.print("ERROR,ERROR");
  } else {
    Serial.print(t, 2); Serial.print(","); Serial.print(h, 2);
  }
  Serial.println('>');
}

// ── PIR sampling ─────────────────────────────────────────────────
void samplePIR() {
  int motion = digitalRead(PIN_PIR);

  Serial.print("<DATA|"); Serial.print(millis());
  Serial.print("|PIR,"); Serial.print(motion);
  Serial.println('>');
}

// ── Command parser ────────────────────────────────────────────────
void processCommand(const String& raw) {
  String verb = raw;
  verb.trim();
  int sep = verb.indexOf('|');
  if (sep >= 0) verb = verb.substring(0, sep);
  verb.toUpperCase();

  if (verb == "STATUS" || verb == "INVENTORY" || verb == "DETECT") {
    sendInventory(); sendHeartbeat();
  } else if (verb == "CONFIG") {
    sendMsg("STATUS", "Config received");
  }
}

void pollSerial() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if      (c == '<') { cmdBuf = ""; }
    else if (c == '>') { if (cmdBuf.length() > 0) { processCommand(cmdBuf); cmdBuf = ""; } }
    else if (cmdBuf.length() < 120) { cmdBuf += c; }
  }
}

// ── Setup / Loop ──────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  while (!Serial) {}   // wait for USB Serial to be ready

  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
  digitalWrite(PIN_TRIG, LOW);

  pinMode(PIN_PIR, INPUT);
  dht.begin();

  sendMsg("STATUS", "MSDA Firmware ready - USB Serial Multi-Sensor");
  sendInventory();
  sendHeartbeat();
  tLastSample = tLastHeartbeat = millis();
}

void loop() {
  unsigned long now = millis();
  pollSerial();

  if (now - tLastHeartbeat >= heartbeatMs) {
    sendHeartbeat(); tLastHeartbeat = now;
  }
  if (now - tLastSample >= sampleIntervalMs) {
    sampleHCSR04();
    sampleDHT();
    samplePIR();
    tLastSample = now;
  }
}
