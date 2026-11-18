// Fan test through L298 driver for ESP32-S3 (HawkerFlow)
// Channel A = the 2 small NMB fans (in parallel), Channel B = the big SF-1225 fan.
//
// Wiring:
//   12V battery +  -> L298 "+12V"     12V battery - -> L298 "GND"
//   L298 GND       -> ESP32 GND  (common ground is REQUIRED)
//   Small fans red -> OUT1, black -> OUT2   (both small fans in parallel)
//   Big fan red    -> OUT3, black -> OUT4
//   REMOVE the ENA and ENB jumpers on the L298, then:
//   ENA -> GPIO 10   IN1 -> GPIO 11   IN2 -> GPIO 12
//   ENB -> GPIO 13   IN3 -> GPIO 14   IN4 -> GPIO 21
//   The ESP32 only sends signals - the fans are powered from 12V, never from a GPIO.
//
// Serial Monitor (115200, "Newline"): type
//   A 60     -> small fans 60 %
//   B 100    -> big fan 100 %
//   A 0      -> small fans off
//   SWEEP A  -> step channel A from 100% down, to find the lowest speed that still spins
// Needs esp32 core 3.x (uses ledcAttach / ledcWrite(pin, duty)).

#define ENA 10
#define IN1 11
#define IN2 12
#define ENB 13
#define IN3 14
#define IN4 21

// 0 = 4-pin L298N (only IN1-IN4, e.g. ZX-040): IN1->11, IN2->12, IN3->14, IN4->21,
//     speed is PWM on IN1/IN3. 1 = 6-pin board with ENA/ENB (wiring above).
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
int MIN_PCT = 35;                 // below this a fan may stall -> treat as off (tune with SWEEP)

int curA = 0, curB = 0;

void setFan(char ch, int pct) {
  pct = constrain(pct, 0, 100);
  if (pct > 0 && pct < MIN_PCT) pct = MIN_PCT;
  int pin = (ch == 'A') ? PWM_A : PWM_B;
  int &cur = (ch == 'A') ? curA : curB;
  if (cur == 0 && pct > 0) {        // kick-start: full power briefly so it starts spinning
    ledcWrite(pin, 255);
    delay(300);
  }
  ledcWrite(pin, map(pct, 0, 100, 0, 255));
  cur = pct;
  Serial.printf("OK  Fan %c = %d %%\n", ch, pct);
}

void sweep(char ch) {
  int saved = MIN_PCT;
  MIN_PCT = 0;  // allow any duty while sweeping
  int pin = (ch == 'A') ? PWM_A : PWM_B;
  ledcWrite(pin, 255);
  delay(1000);
  for (int pct = 100; pct >= 0; pct -= 5) {
    ledcWrite(pin, map(pct, 0, 100, 0, 255));
    Serial.printf("SWEEP %c: %d %%  (watch: does it still spin?)\n", ch, pct);
    delay(2000);
  }
  MIN_PCT = saved;
  if (ch == 'A') curA = 0; else curB = 0;
  Serial.println("Sweep done (fan now off). Set MIN_PCT a little above the lowest spinning value.");
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
  ledcWrite(PWM_A, 0);
  ledcWrite(PWM_B, 0);
  Serial.println("Fan test ready. Commands: A <0-100>, B <0-100>, SWEEP A, SWEEP B");
}

void loop() {
  if (!Serial.available()) return;
  String line = Serial.readStringUntil('\n');
  line.trim();
  line.toUpperCase();
  if (line.startsWith("SWEEP ") && line.length() >= 7) {
    sweep(line.charAt(6));
  } else if ((line.startsWith("A ") || line.startsWith("B ")) && line.length() >= 3) {
    setFan(line.charAt(0), line.substring(2).toInt());
  } else if (line.length() > 0) {
    Serial.println("ERR  use: A 50 | B 100 | SWEEP A");
  }
}
