/*
 * MSDA_Firmware.ino — Issue #2 version: Serial1 (GPIO UART for Raspberry Pi)
 * Protocol: <TYPE|TIMESTAMP_MS|CONTENT>
 *
 * Hardware wiring for Pi communication:
 *   Arduino TX1 → Pi GPIO 15 (RX)
 *   Arduino RX1 → Pi GPIO 14 (TX)
 *   Arduino GND → Pi GND
 *
 * HC-SR04: TRIG → D4, ECHO → D5
 *
 * Pi config: raspi-config → Interface Options → Serial Port
 *   → Login shell: No  → Hardware port: Yes
 */

#define PIN_TRIG  4
#define PIN_ECHO  5

unsigned long sampleIntervalMs = 2000;
unsigned long heartbeatMs      = 5000;
unsigned long tLastSample      = 0;
unsigned long tLastHeartbeat   = 0;

String cmdBuf = "";

// ── Protocol helpers ──────────────────────────────────────────────
void sendMsg(const char* type, const char* content) {
  Serial1.print('<'); Serial1.print(type); Serial1.print('|');
  Serial1.print(millis()); Serial1.print('|');
  Serial1.print(content); Serial1.println('>');
}

void sendHeartbeat() { sendMsg("HEARTBEAT", "OK"); }

void sendInventory() {
  Serial1.print("<INVENTORY|"); Serial1.print(millis());
  Serial1.print("|1|HC_SR04:distance>");
  Serial1.println();
}

// ── HC-SR04 sampling ─────────────────────────────────────────────
void sampleHCSR04() {
  digitalWrite(PIN_TRIG, LOW);  delayMicroseconds(5);
  digitalWrite(PIN_TRIG, HIGH); delayMicroseconds(15);
  digitalWrite(PIN_TRIG, LOW);

  unsigned long dur = pulseIn(PIN_ECHO, HIGH, 60000UL);
  float distCm = dur * 0.01715f;

  Serial1.print("<DATA|"); Serial1.print(millis());
  Serial1.print("|HC_SR04,"); Serial1.print(distCm, 2);
  Serial1.print(",raw_us="); Serial1.print(dur);
  Serial1.println('>');
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
  while (Serial1.available()) {
    char c = (char)Serial1.read();
    if      (c == '<') { cmdBuf = ""; }
    else if (c == '>') { if (cmdBuf.length() > 0) { processCommand(cmdBuf); cmdBuf = ""; } }
    else if (cmdBuf.length() < 120) { cmdBuf += c; }
  }
}

// ── Setup / Loop ──────────────────────────────────────────────────
void setup() {
  // Serial1 = hardware UART (TX1/RX1 pins) → connects to Raspberry Pi GPIO
  Serial1.begin(115200);
  // No "while (!Serial1)" needed — hardware UART is always ready

  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
  digitalWrite(PIN_TRIG, LOW);

  sendMsg("STATUS", "MSDA Firmware ready - GPIO Serial1");
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
    sampleHCSR04(); tLastSample = now;
  }
}
