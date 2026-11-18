// HX710B + MPS20N0040D pressure sensor test for ESP32-S3 (HawkerFlow)
// The sensor measures the pressure in its TUBE compared with the room air.
//
// Wiring (red module, 4 pins: VCC OUT SCK GND):
//   VCC -> 3V3   (NOT 5V)
//   GND -> GND   (black pin)
//   OUT -> GPIO 18 (yellow pin)
//   SCK -> GPIO 17 (yellow pin)
// Tools -> USB CDC On Boot -> Disabled. Serial Monitor 115200.
//
// LIVE CHECK: every second it reports whether the sensor is alive, so you can
// adjust loose header pins until it says "ALIVE". No multimeter needed.
// Once alive: it zeroes on the room pressure (keep the tube still) and prints
// the change 5x per second. Blow gently -> changes one way; suck -> the other.

#define HX_OUT 18
#define HX_SCK 17

const long HX_FAIL = -2147483647L;

long readHX710B() {
  unsigned long t0 = millis();
  while (digitalRead(HX_OUT) == HIGH) {          // LOW = new reading ready
    if (millis() - t0 > 300) return HX_FAIL;
    delay(1);
  }
  long v = 0;
  noInterrupts();                                // SCK must not stay HIGH > 60 us
  for (int i = 0; i < 24; i++) {
    digitalWrite(HX_SCK, HIGH); delayMicroseconds(1);
    v = (v << 1) | digitalRead(HX_OUT);
    digitalWrite(HX_SCK, LOW);  delayMicroseconds(1);
  }
  digitalWrite(HX_SCK, HIGH); delayMicroseconds(1);   // 25th pulse: pressure input, 10 Hz
  digitalWrite(HX_SCK, LOW);  delayMicroseconds(1);
  interrupts();
  if (v & 0x800000) v |= 0xFF000000;
  return v;
}

bool looksReal(long r) { return r != HX_FAIL && r != 0 && r != -1; }

long readAverage(int n) {
  long long sum = 0; int ok = 0;
  for (int i = 0; i < n; i++) { long r = readHX710B(); if (looksReal(r)) { sum += r; ok++; } }
  return ok ? (long)(sum / ok) : HX_FAIL;
}

bool alive = false;
long zero = 0;
int failStreak = 0;

void setup() {
  Serial.begin(115200);
  delay(1000);
  pinMode(HX_SCK, OUTPUT);
  digitalWrite(HX_SCK, LOW);
  pinMode(HX_OUT, INPUT_PULLUP);   // nothing connected -> reads HIGH
  Serial.println("HX710B live check on OUT=GPIO18, SCK=GPIO17. Adjust the pins until it says ALIVE.");
}

void loop() {
  if (!alive) {
    int lows = 0;
    for (int i = 0; i < 400; i++) { if (digitalRead(HX_OUT) == LOW) lows++; delay(1); }
    int good = 0;
    for (int i = 0; i < 3; i++) if (looksReal(readHX710B())) good++;
    if (good >= 2) {
      alive = true;
      Serial.println("ALIVE  sensor connected! Keep the tube still - measuring zero...");
      delay(300);
      zero = readAverage(15);
      Serial.printf("OK  zero = %ld\n", zero);
    } else if (lows == 0) {
      Serial.println("DEAD   no signal on OUT - VCC/GND or OUT pin not touching");
    } else if (lows >= 400) {
      Serial.println("DEAD   OUT stuck low - power pin not touching, or OUT on GND");
    } else {
      Serial.println("WEAK   sensor flickering - contact is close, press/tilt a bit more");
    }
    return;
  }

  long r = readAverage(2);
  if (r == HX_FAIL) {
    if (++failStreak >= 5) { alive = false; failStreak = 0; Serial.println("LOST   contact lost"); }
    return;
  }
  failStreak = 0;
  Serial.printf("OK  raw %ld   change %+ld\n", r, r - zero);
  delay(150);
}
