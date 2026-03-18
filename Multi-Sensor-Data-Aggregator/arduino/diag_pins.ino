/*
 * diag_pins.ino — Pin Diagnostic
 * Check if D7 can toggle and if D8 can read anything.
 */

#define PIN_TRIG 7
#define PIN_ECHO 8

void setup() {
  Serial.begin(115200);
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
  Serial.println("--- Pin Diagnostic Start ---");
}

void loop() {
  // Toggle Trig
  digitalWrite(PIN_TRIG, HIGH);
  delay(500);
  digitalWrite(PIN_TRIG, LOW);
  delay(500);

  // Read Echo
  int val = digitalRead(PIN_ECHO);
  Serial.print("TRIG (D7) toggled. ECHO (D8) read: ");
  Serial.println(val);
}
