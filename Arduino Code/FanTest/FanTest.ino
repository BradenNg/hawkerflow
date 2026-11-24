// Combined fan control through L298 driver for ESP32-S3 (HawkerFlow)
// Channel A = the 2 small NMB fans (in parallel), Channel B = the big SF-1225 fan.
// BOTH channels are always driven at the SAME speed.
//
// Wiring:
//   12V battery +  -> L298 "+12V"     12V battery - -> L298 "GND"
//   L298 GND       -> ESP32 GND  (common ground is REQUIRED)
//   Small fans red -> OUT1, black -> OUT2   (both small fans in parallel)
//   Big fan red    -> OUT3, black -> OUT4
//   4-pin L298N (FAN_HAS_EN 0): IN1 -> GPIO 11, IN2 -> GPIO 12, IN3 -> GPIO 14, IN4 -> GPIO 21
//   6-pin L298 (FAN_HAS_EN 1): remove ENA/ENB jumpers, ENA -> GPIO 10, ENB -> GPIO 13, plus IN1-IN4 as above
//   The ESP32 only sends signals - the fans are powered from 12V, never from a GPIO.
//
// Serial Monitor (115200, "Newline"): type
//   60      -> both fans 60 %
//   100     -> both fans 100 %
//   35      -> both fans at minimum (35 %)
//   0       -> both fans off
//   (1-34 is raised to 35 %, anything above 100 is capped at 100 %)
//   SWEEP   -> step both fans from 100% down to 35%, to check they keep spinning
// Needs esp32 core 3.x (uses ledcAttach / ledcWrite(pin, duty)).

#define ENA 10
#define IN1 11
#define IN2 12
#define ENB 13
#define IN3 14
#define IN4 21

// 0 = 4-pin L298N (only IN1-IN4, e.g. ZX-040): speed is PWM on IN1/IN3.
// 1 = 6-pin board with ENA/ENB: speed is PWM on ENA/ENB.
#define FAN_HAS_EN 0
#if FAN_HAS_EN
  #define PWM_A ENA
  #define PWM_B ENB
#else
  #define PWM_A IN1
  #define PWM_B IN3
#endif

const uint32_t PWM_FREQ = 1000;   // 1 kHz suits the slow L298
const uint8_t  PWM_BITS = 8;      // duty 0..255
const int MIN_PCT = 35;           // lowest speed both fans run at (fan B stalls below this)
const int MAX_PCT = 100;

int curPct = 0;                   // current speed of both fans

// Write the same duty to both channels
void writeBoth(int duty) {
  ledcWrite(PWM_A, duty);
  ledcWrite(PWM_B, duty);
}

int pctToDuty(int pct) {
  return map(pct, 0, 100, 0, 255);
}

void setFans(int pct) {
  if (pct <= 0) {
    pct = 0;                                  // off
  } else {
    pct = constrain(pct, MIN_PCT, MAX_PCT);   // 35..100
  }

  if (curPct == 0 && pct > 0) {   // kick-start: full power briefly so both start spinning
    writeBoth(255);
    delay(300);
  }

  writeBoth(pctToDuty(pct));
  curPct = pct;

  if (pct == 0) Serial.println("OK  Fans OFF");
  else          Serial.printf("OK  Both fans = %d %%\n", pct);
}

void sweep() {
  writeBoth(255);
  delay(1000);
  for (int pct = MAX_PCT; pct >= MIN_PCT; pct -= 5) {
    writeBoth(pctToDuty(pct));
    Serial.printf("SWEEP: %d %%  (watch: do both still spin?)\n", pct);
    delay(2000);
  }
  writeBoth(0);
  curPct = 0;
  Serial.println("Sweep done (fans now off).");
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  pinMode(IN2, OUTPUT); digitalWrite(IN2, LOW);
  pinMode(IN4, OUTPUT); digitalWrite(IN4, LOW);
#if FAN_HAS_EN
  pinMode(IN1, OUTPUT); digitalWrite(IN1, HIGH);   // channel A: forward
  pinMode(IN3, OUTPUT); digitalWrite(IN3, HIGH);   // channel B: forward
#endif
  if (!ledcAttach(PWM_A, PWM_FREQ, PWM_BITS) || !ledcAttach(PWM_B, PWM_FREQ, PWM_BITS)) {
    Serial.println("FAIL: ledcAttach failed");
  }
  writeBoth(0);
  Serial.println("Fan control ready. Type a speed 35-100 (0 = off), or SWEEP");
}

void loop() {
  if (!Serial.available()) return;
  String line = Serial.readStringUntil('\n');
  line.trim();
  line.toUpperCase();
  if (line.length() == 0) return;

  if (line == "SWEEP") {
    sweep();
  } else if (isDigit(line.charAt(0))) {
    setFans(line.toInt());
  } else {
    Serial.println("ERR  use: 60 | 100 | 0 | SWEEP");
  }
}
