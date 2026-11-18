// 360-degree (continuous rotation) servo test for the HawkerFlow damper flap
// Wiring:
//   Servo brown/black -> GND (common with ESP32 GND)
//   Servo red         -> 5V from buck converter (or L298 "+5V" pin with 12V battery on)
//                        -- NOT the ESP32 3V3
//   Servo orange      -> GPIO 15
// No library needed (drives the servo with the ESP32's own PWM, same as HawkerFlow.ino).
// Tools -> USB CDC On Boot -> Disabled (so you see the output on COM6)
//
// A 360 servo cannot go to an angle - it only spins one way or the other.
// So a "small turn" = spin for a few hundred milliseconds, then stop.
//
// Serial Monitor (115200, "Newline"):
//   CLOSE       -> one small turn in the closing direction
//   OPEN        -> one small turn back (opposite direction)
//   TIME n      -> set how long a small turn lasts, in ms (e.g. TIME 200)
//   SPEED n     -> set spin speed 50..500 (e.g. SPEED 100 = slower)
//   TRIM n      -> hold the "stop" pulse n us (try 1500, 1480, 1520...) for 2 s.
//                  Use it if the servo creeps instead of standing still.
//   STOP        -> stop immediately
// When the flap moves the right amount, copy TIME, SPEED and the stop value
// into TURN_MS, SERVO_SPEED_US and SERVO_STOP_US in HawkerFlow.ino.
// If CLOSE turns the wrong way, set CLOSE_DIR = 1 in both files.

#define SERVO_PIN 15
int SERVO_STOP_US  = 1500;
int SERVO_SPEED_US = 400;
int TURN_MS        = 800;
int CLOSE_DIR      = -1;

void servoPulse(int us) {   // 50 Hz, 14-bit; us = 0 -> no pulses (idle)
  ledcWrite(SERVO_PIN, (uint32_t)us * 16384UL / 20000UL);
}

void servoOff() {
  servoPulse(SERVO_STOP_US);
  delay(100);
  servoPulse(0);
}

void spin(int dir, int ms) {
  servoPulse(SERVO_STOP_US + dir * SERVO_SPEED_US);
  delay(ms);
  servoOff();
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  if (!ledcAttachChannel(SERVO_PIN, 50, 14, 4)) Serial.println("FAIL: servo PWM setup");
  servoPulse(0);   // servo does not move at start-up
  Serial.println("360 servo test. Commands: CLOSE, OPEN, TIME n, SPEED n, TRIM n, STOP");
}

void loop() {
  if (!Serial.available()) return;
  String line = Serial.readStringUntil('\n');
  line.trim();
  line.toUpperCase();
  if (line == "CLOSE") {
    spin(CLOSE_DIR, TURN_MS);
    Serial.printf("OK  closed a bit (%d ms at speed %d)\n", TURN_MS, SERVO_SPEED_US);
  } else if (line == "OPEN") {
    spin(-CLOSE_DIR, TURN_MS);
    Serial.printf("OK  opened a bit (%d ms at speed %d)\n", TURN_MS, SERVO_SPEED_US);
  } else if (line.startsWith("TIME ")) {
    TURN_MS = constrain(line.substring(5).toInt(), 20, 3000);
    Serial.printf("OK  TURN_MS = %d\n", TURN_MS);
  } else if (line.startsWith("SPEED ")) {
    SERVO_SPEED_US = constrain(line.substring(6).toInt(), 50, 500);
    Serial.printf("OK  SERVO_SPEED_US = %d\n", SERVO_SPEED_US);
  } else if (line.startsWith("TRIM ")) {
    SERVO_STOP_US = constrain(line.substring(5).toInt(), 1300, 1700);
    spin(0, 2000);   // hold the stop pulse - the servo should NOT turn
    Serial.printf("OK  SERVO_STOP_US = %d (did it stay still?)\n", SERVO_STOP_US);
  } else if (line == "STOP") {
    servoPulse(0);
    Serial.println("OK  stopped");
  } else if (line.length() > 0) {
    Serial.println("ERR  use: CLOSE | OPEN | TIME 300 | SPEED 150 | TRIM 1500 | STOP");
  }
}
