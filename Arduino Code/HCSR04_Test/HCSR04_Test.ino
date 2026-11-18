// HC-SR04 ultrasonic test for ESP32-S3 (HawkerFlow blockage sensor)
// Wiring:
//   HC-SR04 VCC  -> 5V pin on ESP32 board
//   HC-SR04 GND  -> GND
//   HC-SR04 TRIG -> GPIO 5   (3.3V trigger is fine)
//   HC-SR04 ECHO -> 1k resistor -> GPIO 6 ; GPIO 6 -> 2k resistor -> GND
//                   (voltage divider: ECHO is 5V, the ESP32 pin only takes 3.3V!)
// No library needed.
// Test: point it into the duct. Put a card/hand in the duct -> distance should drop.

#define TRIG_PIN 5
#define ECHO_PIN 6

const unsigned long ECHO_TIMEOUT_US = 25000;  // ~4 m max; no echo -> -1

// One ping. Returns distance in cm, or -1 if no echo.
float pingOnce() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  unsigned long us = pulseIn(ECHO_PIN, HIGH, ECHO_TIMEOUT_US);
  if (us == 0) return -1;
  return us / 58.0;  // speed of sound: 58 us per cm (there and back)
}

// Median of 5 pings removes the occasional wild reading.
float readDistanceCm() {
  float v[5];
  int n = 0;
  for (int i = 0; i < 5; i++) {
    float d = pingOnce();
    if (d > 0) v[n++] = d;
    delay(10);  // let echoes die out between pings
  }
  if (n == 0) return -1;
  // simple insertion sort
  for (int i = 1; i < n; i++) {
    float k = v[i];
    int j = i - 1;
    while (j >= 0 && v[j] > k) { v[j + 1] = v[j]; j--; }
    v[j + 1] = k;
  }
  return v[n / 2];
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  Serial.println("HC-SR04 test starting...");
}

void loop() {
  float d = readDistanceCm();
  if (d < 0) {
    Serial.println("FAIL: no echo - check wiring/divider, or nothing within range");
  } else {
    Serial.print("OK  Distance: ");
    Serial.print(d, 1);
    Serial.println(" cm");
  }
  delay(200);
}
