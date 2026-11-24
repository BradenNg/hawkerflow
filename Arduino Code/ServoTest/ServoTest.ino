// Servo test for the two HawkerFlow damper servos
//   Servo 2: Airtecnic AT-46, normal 180-degree servo (works like an MG90S) -> GPIO 7
//            OPEN = 90 degrees, CLOSE = 0 degrees
//   Servo 1: 360-degree (continuous rotation) damper flap                    -> GPIO 15
// Wiring (both servos):
//   Servo brown/black -> GND (common with ESP32 GND)
//   Servo red         -> 5V from buck converter (or L298 "+5V" pin with 12V battery on)
//                        -- NOT the ESP32 3V3
//   Servo orange      -> GPIO 7 (AT-46) / GPIO 15 (360 servo)
// No library needed (drives the servos with the ESP32's own PWM, same as HawkerFlow.ino:
// servo 1 on LEDC channel 4, servo 2 on channel 5).
// Tools -> USB CDC On Boot -> Disabled (so you see the output on COM6)
//
// Serial Monitor (115200, "Newline"):
//  AT-46 (GPIO 7):
//   OPEN        -> go to OPEN_DEG  (90 degrees) and hold it there
//   CLOSE       -> go to CLOSE_DEG (0 degrees)  and hold it there
//   ANGLE n     -> go to any angle 0..180 (to find good OPEN/CLOSE values)
//  360 servo (GPIO 15) - it can't go to an angle, it only spins for a short time:
//   OPEN1       -> one small turn in the opening direction
//   CLOSE1      -> one small turn in the closing direction
//   TIME n      -> how long a small turn lasts, in ms (e.g. TIME 200)
//   SPEED n     -> spin speed 50..500 (e.g. SPEED 100 = slower)
//   TRIM n      -> hold the "stop" pulse n us (try 1500, 1480, 1520...) for 2 s.
//                  Use it if the servo creeps instead of standing still.
//  Both:
//   STOP        -> stop sending pulses to both servos (AT-46 goes limp)
// Copy the AT-46 angles into SERVO2_OPEN_DEG / SERVO2_CLOSED_DEG in HawkerFlow.ino,
// and TIME / SPEED / stop value into TURN_MS / SERVO_SPEED_US / SERVO_STOP_US.

#define SERVO_PIN  15   // servo 1: 360-degree damper flap
#define SERVO2_PIN 7    // servo 2: Airtecnic AT-46 (180-degree, like an MG90S)

// AT-46 positions
const int OPEN_DEG  = 90;
const int CLOSE_DEG = 0;

// 360 servo settings
int SERVO_STOP_US  = 1500;
int SERVO_SPEED_US = 400;
int TURN_MS        = 800;
int CLOSE_DIR      = -1;

void servoPulse(int pin, int us) {   // 50 Hz, 14-bit; us = 0 -> no pulses (idle)
  ledcWrite(pin, (uint32_t)us * 16384UL / 20000UL);
}

// Same angle -> pulse mapping as HawkerFlow.ino (0 deg = 500 us, 180 deg = 2400 us)
int degToUs(int deg) { return 500 + (long)constrain(deg, 0, 180) * 1900 / 180; }

// Like servo.write(deg) on an MG90S: go to the angle and KEEP holding it.
void at46Write(int deg) {
  servoPulse(SERVO2_PIN, degToUs(deg));
}

void spin(int dir, int ms) {
  servoPulse(SERVO_PIN, SERVO_STOP_US + dir * SERVO_SPEED_US);
  delay(ms);
  servoPulse(SERVO_PIN, SERVO_STOP_US);
  delay(100);
  servoPulse(SERVO_PIN, 0);
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  if (!ledcAttachChannel(SERVO_PIN, 50, 14, 4))  Serial.println("FAIL: servo 1 (GPIO 15) PWM setup");
  if (!ledcAttachChannel(SERVO2_PIN, 50, 14, 5)) Serial.println("FAIL: servo 2 (GPIO 7) PWM setup");
  servoPulse(SERVO_PIN, 0);    // 360 servo does not move at start-up
  servoPulse(SERVO2_PIN, 0);   // AT-46 waits for OPEN / CLOSE
  Serial.println("Servo test. AT-46 (GPIO 7): OPEN (90), CLOSE (0), ANGLE n");
  Serial.println("            360 servo (GPIO 15): OPEN1, CLOSE1, TIME n, SPEED n, TRIM n   Both: STOP");
}

void loop() {
  if (!Serial.available()) return;
  String line = Serial.readStringUntil('\n');
  line.trim();
  line.toUpperCase();

  // ---- AT-46 ----
  if (line == "OPEN") {
    at46Write(OPEN_DEG);
    Serial.printf("OK  AT-46 OPEN  (%d deg, %d us)\n", OPEN_DEG, degToUs(OPEN_DEG));
  } else if (line == "CLOSE") {
    at46Write(CLOSE_DEG);
    Serial.printf("OK  AT-46 CLOSE (%d deg, %d us)\n", CLOSE_DEG, degToUs(CLOSE_DEG));
  } else if (line.startsWith("ANGLE ")) {
    int deg = constrain(line.substring(6).toInt(), 0, 180);
    at46Write(deg);
    Serial.printf("OK  AT-46 ANGLE %d (%d us)\n", deg, degToUs(deg));

  // ---- 360 servo ----
  } else if (line == "CLOSE1") {
    spin(CLOSE_DIR, TURN_MS);
    Serial.printf("OK  360 servo closed a bit (%d ms at speed %d)\n", TURN_MS, SERVO_SPEED_US);
  } else if (line == "OPEN1") {
    spin(-CLOSE_DIR, TURN_MS);
    Serial.printf("OK  360 servo opened a bit (%d ms at speed %d)\n", TURN_MS, SERVO_SPEED_US);
  } else if (line.startsWith("TIME ")) {
    TURN_MS = constrain(line.substring(5).toInt(), 20, 3000);
    Serial.printf("OK  TURN_MS = %d\n", TURN_MS);
  } else if (line.startsWith("SPEED ")) {
    SERVO_SPEED_US = constrain(line.substring(6).toInt(), 50, 500);
    Serial.printf("OK  SERVO_SPEED_US = %d\n", SERVO_SPEED_US);
  } else if (line.startsWith("TRIM ")) {
    SERVO_STOP_US = constrain(line.substring(5).toInt(), 1300, 1700);
    spin(0, 2000);   // hold the stop pulse - the 360 servo should NOT turn
    Serial.printf("OK  SERVO_STOP_US = %d (did it stay still?)\n", SERVO_STOP_US);

  // ---- both ----
  } else if (line == "STOP") {
    servoPulse(SERVO_PIN, 0);
    servoPulse(SERVO2_PIN, 0);
    Serial.println("OK  both stopped");
  } else if (line.length() > 0) {
    Serial.println("ERR  use: OPEN | CLOSE | ANGLE 45 | OPEN1 | CLOSE1 | TIME 300 | SPEED 150 | TRIM 1500 | STOP");
  }
}
