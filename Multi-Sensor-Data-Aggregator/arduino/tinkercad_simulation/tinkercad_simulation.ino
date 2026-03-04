/*
 * MSDA — Issue #1 Simulation Sketch (Tinkercad)
 * Sensors: HC-SR04 (Ultrasonic) + PIR (Motion)
 *
 * Pin mapping (matches real SensorHub.cpp):
 *   HC-SR04 TRIG → D4
 *   HC-SR04 ECHO → D5
 *   PIR OUT      → D6
 *
 * Serial Monitor baud: 9600
 */

#define PIN_TRIG  4
#define PIN_ECHO  5
#define PIN_PIR   6

const unsigned long INTERVAL = 2000;
unsigned long lastTime = 0;

void setup() {
  Serial.begin(9600);
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
  pinMode(PIN_PIR,  INPUT);
  Serial.println("=== MSDA Issue #1 — Sensor Test ===");
  Serial.println("Sensors: HC-SR04 | PIR");
  Serial.println("-----------------------------------");
}

float getDistance() {
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);
  long dur = pulseIn(PIN_ECHO, HIGH, 30000UL);
  return dur * 0.01715;   // microseconds → cm
}

void loop() {
  unsigned long now = millis();
  if (now - lastTime < INTERVAL) return;
  lastTime = now;

  float distCm = getDistance();
  int   motion  = digitalRead(PIN_PIR);

  // Human-readable output
  Serial.print("Distance: "); Serial.print(distCm, 1); Serial.println(" cm");
  Serial.print("Motion  : "); Serial.println(motion ? "DETECTED" : "none");

  // JSON output (matches real SensorHub format for the Pi)
  Serial.print("{\"type\":\"DATA\",\"ts\":"); Serial.print(now);
  Serial.print(",\"sensor\":\"HC_SR04\",\"values\":{\"distance_cm\":"); Serial.print(distCm, 1);
  Serial.println("}}");

  Serial.print("{\"type\":\"DATA\",\"ts\":"); Serial.print(now);
  Serial.print(",\"sensor\":\"PIR\",\"values\":{\"motion\":"); Serial.print(motion);
  Serial.println("}}");

  Serial.println();
}
