// =====================================================================
//  HawkerFlow – main ESP32-S3 firmware (Person 2)
//
//  Every 2 s: read DHT22 + pressure sensor, send one CSV line to the laptop.
//  Laptop (Python AI) answers  PREDICTION:NORMAL | COOKING | BLOCKED
//  ESP32 sets fans, LEDs and LCD for that state.
//
//  Wiring (same as the test sketches):
//    DHT22 DATA -> 4
//    L298 IN1/IN2 -> 11/12  (2 small fans, in parallel, OUT1/OUT2)
//    L298 IN3/IN4 -> 14/21  (big fan, OUT3/OUT4)
//    (6-pin L298N only: ENA -> 10, ENB -> 13, jumpers removed; set FAN_HAS_EN 1)
//    Servo 1 (damper flap) -> 15, Servo 2 (AT-46 damper) -> 7 (both powered from 5 V)
//    LEDs R/Y/G -> 16/38/39    LCD I2C SDA/SCL -> 8/9
//    Pressure sensor HX710B: VCC -> 3V3, OUT -> 18, SCK -> 17 (tube into the duct)
//    Common GND for battery, L298, servo and ESP32.
//
//  Libraries: DHT sensor library, Adafruit Unified Sensor (servo needs no library),
//             LiquidCrystal I2C.   Board: ESP32S3 Dev Module, core 3.x.
//
//  ---------------- Serial protocol (115200 baud, '\n' line endings) ----
//  ESP32 -> laptop:
//    HEADER,millis,temp_c,humidity,pressure,fan_a_pct,fan_b_pct,damper_closed,rpm_a,rpm_b,state
//    pressure = change in duct pressure since power-on, in thousands of sensor
//    counts (+ = higher than room, - = lower). "ZERO" resets it.
//    DATA,<values in the same order>          (every 2 s)
//    ACK,<what was accepted>   /   ERR,<why>   (replies to commands)
//    Lines that do not start with DATA are info - Python should ignore them.
//  Laptop -> ESP32:
//    PREDICTION:NORMAL | PREDICTION:COOKING | PREDICTION:BLOCKED
//    DAMPER CLOSE  (simulate a blocked duct; pauses automatic damper moves; small fan OFF)
//    DAMPER OPEN   (open it, return the damper to automatic; small fan ON)
//    FAN A <0-100> | FAN B <0-100> (switches to MANUAL mode)
//    MODE AUTO | MODE MANUAL       STATUS
//
//  NOTE for the AI team: fan_a_pct, fan_b_pct, damper_closed and state are
//  OUTPUTS of the system, logged for the record. Do NOT train the model on
//  them – use temp_c, humidity, pressure (and rpm if tach is enabled).
// =====================================================================

#include <Wire.h>
#include <DHT.h>
#include <LiquidCrystal_I2C.h>

// ---------------- Pins ----------------
#define DHT_PIN   4
#define SDA_PIN   8
#define SCL_PIN   9
#define ENA       10
#define IN1       11
#define IN2       12
#define ENB       13
#define IN3       14
#define IN4       21
#define SERVO_PIN 15
#define SERVO2_PIN 7
#define LED_R     16
#define LED_Y     38       // moved from 17 (17/18 now used by the pressure sensor)
#define LED_G     39       // moved from 18
#define HX_OUT    18       // HX710B pressure sensor OUT
#define HX_SCK    17       // HX710B pressure sensor SCK
#define TACH_A    1
#define TACH_B    2

// L298N type:
//  0 = 4-pin board (only IN1 IN2 IN3 IN4, e.g. ZX-040): speed is PWM on IN1/IN3.
//      Wire IN1->11, IN2->12, IN3->14, IN4->21. GPIO 10 and 13 are not used.
//  1 = 6-pin board (ENA IN1 IN2 IN3 IN4 ENB): speed is PWM on ENA/ENB (10/13).
#define FAN_HAS_EN 0

// ---------------- Settings to tune (with Persons 1, 3, 4) --------------
#define USE_TACH 0                 // 1 only if the fans have a 3rd (tach) wire
const uint8_t LCD_ADDR = 0x27;     // from LcdLedTest (0x27 or 0x3F)

const unsigned long SAMPLE_MS      = 2000;   // send readings every 2 s
const unsigned long AI_TIMEOUT_MS  = 10000;  // no prediction for 10 s -> AI offline
const int  PREDICTIONS_TO_SWITCH   = 2;      // same prediction N times in a row before acting

const int  MIN_FAN_PCT     = 35;   // from FanTest SWEEP: below this the fan stalls
const unsigned long KICK_MS = 300; // full power briefly when a fan starts

// Damper flap (servo). Three positions, one "small turn" apart:
//   CLOSED  <-- small turn --  OPEN  -- small turn -->  RELIEF
//  OPEN   = normal position (NORMAL / COOKING)
//  RELIEF = AUTOMATIC on BLOCKED: flap turns a bit further OUT of the duct
//           to give the air as much room as possible; back to OPEN when clear.
//  CLOSED = manual test only ("DAMPER CLOSE") to SIMULATE a blockage.
// It only moves when its target changes, and is switched off afterwards.
const bool AUTO_DAMPER = true;     // false = damper only moves on DAMPER commands

// Your servo is a 360-degree (continuous rotation) type: it can't go to an
// angle, it can only spin one way or the other. So a "small turn" = spin for
// TURN_MS milliseconds, then stop. Tune these 3 numbers with ServoTest.
// It has no position feedback: put the flap in the OPEN position by hand
// before powering on.
const bool SERVO_360      = true;
const int  SERVO_STOP_US  = 1500;  // pulse that means "stop" (ServoTest: TRIM)
const int  SERVO_SPEED_US = 400;   // spin speed: 100 = slow ... 500 = fast
const int  TURN_MS        = 300;   // how long one small turn lasts
const int  CLOSE_DIR      = -1;    // change to 1 if CLOSE turns the wrong way

// Only used if SERVO_360 = false (normal 180-degree positional servo).
const int  DAMPER_OPEN_DEG   = 90;
const int  DAMPER_CLOSED_DEG = 60;
const int  DAMPER_RELIEF_DEG = 120;

// Second damper servo: Airtecnic AT-46 on GPIO 7 (black GND, red 5V, orange 7).
// It moves together with the first one, the same way (timed small turn).
// Tune it on its own with the "SERVO2 <us>" command, e.g. SERVO2 1000.
const bool USE_SERVO2      = true;
const bool SERVO2_360      = false;  // AT-46 is a normal 180-degree servo (goes to an angle)
const int  SERVO2_STOP_US  = 1500;
const int  SERVO2_SPEED_US = 400;
const int  SERVO2_TURN_MS  = 300;
const int  SERVO2_CLOSE_DIR = -1;    // change to 1 if it closes the wrong way
const int  SERVO2_OPEN_DEG   = 90;   // used because SERVO2_360 = false; bigger gap = bigger turn
const int  SERVO2_CLOSED_DEG = 60;
const int  SERVO2_RELIEF_DEG = 120;

struct ServoCfg {
  int pin; bool on; bool is360; int stopUs; int speedUs; int turnMs; int closeDir;
  int openDeg; int closedDeg; int reliefDeg;
};

// Pressure safety override: if |pressure| stays above PRESSURE_BLOCK for
// BLOCK_READS readings in a row, go BLOCKED even if the AI disagrees.
// 0 = off. Set it after testing the tube in the duct (open vs closed damper).
const float PRESSURE_BLOCK  = 0;
const int   BLOCK_READS     = 3;

// Small fan (A): true = always spinning (speed follows the table below).
// false = OFF at power-on; "DAMPER OPEN" switches it on, "DAMPER CLOSE" off.
const bool SMALL_FAN_ALWAYS_ON = true;

// Fan PWM frequency. Small 2-wire fans ignore fast PWM (they just run full
// speed); a slow PWM (30-100 Hz) gives real speed control but may tick a bit.
// Try others live with the command  FANHZ <n>  (e.g. FANHZ 50).
const uint32_t FAN_PWM_HZ = 50;     // tested: small fan only changes speed at slow PWM
const uint8_t  FAN_PWM_BITS = 12;           // 12-bit allows ~20 Hz .. 19 kHz
const uint32_t FAN_PWM_MAX = (1 << FAN_PWM_BITS) - 1;

//               fan A (small) , fan B (big)
const int NORMAL_A  = 40,  NORMAL_B  = 30;
const int COOKING_A = 100, COOKING_B = 100;
const int BLOCKED_A = 50,  BLOCKED_B = 100;
const int OFFLINE_A = 50,  OFFLINE_B = 50;

// ---------------- Objects / state ----------------
DHT dht(DHT_PIN, DHT22);
LiquidCrystal_I2C lcd(LCD_ADDR, 16, 2);
bool lcdOk = false;

enum State { NORMAL, COOKING, BLOCKED, OFFLINE };
const char *STATE_NAME[] = { "NORMAL", "COOKING", "BLOCKED", "OFFLINE" };

State aiState = OFFLINE;        // last confirmed AI prediction
State shownState = OFFLINE;     // what the system is actually doing
bool manualMode = false;
bool localBlocked = false;      // pressure safety override
int  blockReads = 0;

State pendingPred = OFFLINE;
int   pendingCount = 0;
unsigned long lastPredMs = 0;
bool  everGotPred = false;

int  fanPct[2] = { 0, 0 };              // [0]=A, [1]=B
unsigned long kickUntil[2] = { 0, 0 };
bool damperClosed = false;
bool fanAEnabled = SMALL_FAN_ALWAYS_ON; // false: small fan runs only after DAMPER OPEN

float lastTemp = NAN, lastHum = NAN;
float lastPressure = NAN;     // change since zero, in 1000s of counts
long  pressureZero = 0;
bool  pressureOk = false;
int   pressureFails = 0;
float rpmA = -1, rpmB = -1;

unsigned long lastSampleMs = 0;
char rxBuf[64];
uint8_t rxLen = 0;

#if USE_TACH
volatile uint32_t tachCount[2] = { 0, 0 };
void IRAM_ATTR tachIsrA() { tachCount[0]++; }
void IRAM_ATTR tachIsrB() { tachCount[1]++; }
#endif

// ---------------- Fans ----------------
// The pin that carries the speed (PWM) signal for each channel.
#if FAN_HAS_EN
int enPin(int ch) { return ch == 0 ? ENA : ENB; }
#else
int enPin(int ch) { return ch == 0 ? IN1 : IN3; }
#endif

void setFan(int ch, int pct) {
  pct = constrain(pct, 0, 100);
  if (pct > 0 && pct < MIN_FAN_PCT) pct = MIN_FAN_PCT;
  if (pct == fanPct[ch]) return;
  if (fanPct[ch] == 0 && pct > 0) {
    kickUntil[ch] = millis() + KICK_MS;   // start at full power, drop later in updateFans()
    ledcWrite(enPin(ch), FAN_PWM_MAX);
  } else {
    kickUntil[ch] = 0;
    ledcWrite(enPin(ch), map(pct, 0, 100, 0, FAN_PWM_MAX));
  }
  fanPct[ch] = pct;
}

void updateFans() {   // finish kick-starts without blocking
  for (int ch = 0; ch < 2; ch++) {
    if (kickUntil[ch] && (long)(millis() - kickUntil[ch]) >= 0) {
      kickUntil[ch] = 0;
      ledcWrite(enPin(ch), map(fanPct[ch], 0, 100, 0, FAN_PWM_MAX));
    }
  }
}

// ---------------- Damper ----------------
const int POS_CLOSED = -1, POS_OPEN = 0, POS_RELIEF = 1;
const char *POS_NAME[] = { "CLOSED", "OPEN", "RELIEF" };   // index = pos + 1
int  damperPos  = POS_OPEN;  // assumed: flap set OPEN by hand before power-on
bool damperHold = false;     // true after "DAMPER CLOSE": automatic moves paused

// Each servo is driven directly by the ESP32's LEDC PWM on its OWN channel
// (no servo library), so it can't clash with the fan PWM channels.
// 50 Hz, 14-bit: duty = pulse_us * 16384 / 20000.
const ServoCfg SERVOS[2] = {
  { SERVO_PIN,  true,       SERVO_360,  SERVO_STOP_US,  SERVO_SPEED_US,  TURN_MS,        CLOSE_DIR,
    DAMPER_OPEN_DEG, DAMPER_CLOSED_DEG, DAMPER_RELIEF_DEG },
  { SERVO2_PIN, USE_SERVO2, SERVO2_360, SERVO2_STOP_US, SERVO2_SPEED_US, SERVO2_TURN_MS, SERVO2_CLOSE_DIR,
    SERVO2_OPEN_DEG, SERVO2_CLOSED_DEG, SERVO2_RELIEF_DEG },
};

void servoPulse(int pin, int us) {     // us = 0 -> no pulses at all (servo idle)
  ledcWrite(pin, (uint32_t)us * 16384UL / 20000UL);
}

int degToUs(int deg) { return 500 + (long)constrain(deg, 0, 180) * 1900 / 180; }

int posToDeg(const ServoCfg &s, int pos) {
  return pos == POS_CLOSED ? s.closedDeg : pos == POS_RELIEF ? s.reliefDeg : s.openDeg;
}

void servoOff(const ServoCfg &s) {
  servoPulse(s.pin, s.is360 ? s.stopUs : 0);   // "stop" pulse first
  delay(100);
  servoPulse(s.pin, 0);                        // then no signal -> stays still
}

// Both servos start together; each stops after its own time.
void moveDamper(int target) {
  if (target == damperPos) return;          // already there: don't move
  int steps = target - damperPos;            // e.g. OPEN->CLOSED = -1, CLOSED->RELIEF = +2
  unsigned long runMs[2] = { 0, 0 };

  for (int i = 0; i < 2; i++) {
    const ServoCfg &s = SERVOS[i];
    if (!s.on) continue;
    if (s.is360) {
      int dir = (steps < 0) ? s.closeDir : -s.closeDir;
      servoPulse(s.pin, s.stopUs + dir * s.speedUs);    // spin...
      runMs[i] = abs(steps) * s.turnMs;                 // ...a bit
    } else {
      servoPulse(s.pin, degToUs(posToDeg(s, target)));  // go to the angle
      runMs[i] = 500;
    }
  }
  unsigned long t0 = millis();
  bool done[2] = { !SERVOS[0].on, !SERVOS[1].on };
  while (!done[0] || !done[1]) {
    for (int i = 0; i < 2; i++) {
      if (!done[i] && millis() - t0 >= runMs[i]) {
        servoPulse(SERVOS[i].pin, SERVOS[i].is360 ? SERVOS[i].stopUs : 0);  // stop this one
        done[i] = true;
      }
    }
    delay(1);
  }
  delay(100);
  for (int i = 0; i < 2; i++) if (SERVOS[i].on) servoPulse(SERVOS[i].pin, 0);

  damperPos = target;
  damperClosed = (target == POS_CLOSED);
}

// Manual DAMPER commands. CLOSE holds the flap closed (test blockage) and pauses
// the automatic moves; OPEN opens it and hands control back to automatic.
void setDamper(bool closed) {
  damperHold = closed;
  moveDamper(closed ? POS_CLOSED : POS_OPEN);
}

// ---------------- Sensors ----------------
// HX710B pressure sensor (24-bit, ~10 readings per second).
const long HX_FAIL = -2147483647L;

long readHX710B() {
  unsigned long t0 = millis();
  while (digitalRead(HX_OUT) == HIGH) {          // LOW = new reading ready
    if (millis() - t0 > 150) return HX_FAIL;
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
  return (v == 0 || v == -1) ? HX_FAIL : v;      // all 0s / all 1s = not connected
}

long readPressureAvg(int n) {
  long long sum = 0; int ok = 0;
  for (int i = 0; i < n; i++) { long r = readHX710B(); if (r != HX_FAIL) { sum += r; ok++; } }
  return ok ? (long)(sum / ok) : HX_FAIL;
}

void zeroPressure() {                            // current pressure becomes "0"
  long z = readPressureAvg(10);
  pressureOk = (z != HX_FAIL);
  if (pressureOk) pressureZero = z;
}

void readSensors(unsigned long dtMs) {
  lastTemp = dht.readTemperature();   // NAN on failure -> sent as "nan"
  lastHum  = dht.readHumidity();
  if (!pressureOk) {                    // sensor missing at start / contact lost: retry
    zeroPressure();
    if (pressureOk) Serial.println("INFO,pressure sensor connected - zeroed");
  }
  long p = readPressureAvg(3);
  lastPressure = (pressureOk && p != HX_FAIL) ? (p - pressureZero) / 1000.0 : NAN;
  if (pressureOk && p == HX_FAIL && ++pressureFails >= 3) {   // lost for 3 readings in a row
    pressureOk = false;
    pressureFails = 0;
    Serial.println("INFO,pressure sensor lost - check OUT 18 / SCK 17 / 3V3 / GND contact");
  } else if (p != HX_FAIL) {
    pressureFails = 0;
  }

  // Pressure safety override (off while PRESSURE_BLOCK = 0).
  if (PRESSURE_BLOCK > 0 && !isnan(lastPressure) && fabs(lastPressure) > PRESSURE_BLOCK) blockReads++;
  else blockReads = 0;
  localBlocked = blockReads >= BLOCK_READS;

#if USE_TACH
  noInterrupts();
  uint32_t a = tachCount[0], b = tachCount[1];
  tachCount[0] = tachCount[1] = 0;
  interrupts();
  // most PC fans give 2 pulses per revolution
  rpmA = a * 60000.0 / 2.0 / dtMs;
  rpmB = b * 60000.0 / 2.0 / dtMs;
#endif
}

void sendData() {
  Serial.printf("DATA,%lu,", millis());
  Serial.print(lastTemp, 1);  Serial.print(',');
  Serial.print(lastHum, 1);   Serial.print(',');
  Serial.print(lastPressure, 1); Serial.print(',');
  Serial.printf("%d,%d,%d,", fanPct[0], fanPct[1], damperClosed ? 1 : 0);
  Serial.print(rpmA, 0);      Serial.print(',');
  Serial.print(rpmB, 0);      Serial.print(',');
  Serial.println(manualMode ? "MANUAL" : STATE_NAME[shownState]);
}

// ---------------- State -> outputs ----------------
void applyFans() {
  if (manualMode) return;   // fans stay where FAN commands put them
  int a = OFFLINE_A, b = OFFLINE_B;
  switch (shownState) {
    case NORMAL:  a = NORMAL_A;  b = NORMAL_B;  break;
    case COOKING: a = COOKING_A; b = COOKING_B; break;
    case BLOCKED: a = BLOCKED_A; b = BLOCKED_B; break;
    case OFFLINE: a = OFFLINE_A; b = OFFLINE_B; break;
  }
  setFan(0, fanAEnabled ? a : 0);
  setFan(1, b);
}

void applyState() {
  if (!manualMode && (millis() - lastPredMs > AI_TIMEOUT_MS || !everGotPred)) aiState = OFFLINE;
  shownState = localBlocked ? BLOCKED : aiState;
  if (manualMode) return;
  applyFans();
  // Damper: automatic only on a real state (not OFFLINE, so no move at start-up),
  // and never while a manual "DAMPER CLOSE" test blockage is being held.
  if (AUTO_DAMPER && !damperHold) {
    if (shownState == BLOCKED) moveDamper(POS_RELIEF);
    else if (shownState == NORMAL || shownState == COOKING) moveDamper(POS_OPEN);
  }
}

void updateLeds() {
  bool blink = (millis() / 400) % 2;
  bool r = false, y = false, g = false;
  if (manualMode)                 { y = true; }
  else switch (shownState) {
    case NORMAL:  g = true;  break;
    case COOKING: y = true;  break;
    case BLOCKED: r = blink; break;
    case OFFLINE: y = blink; break;
  }
  digitalWrite(LED_R, r);
  digitalWrite(LED_Y, y);
  digitalWrite(LED_G, g);
}

void updateLcd() {
  if (!lcdOk) return;
  char l1[17], l2[17];
  if (manualMode)                  snprintf(l1, sizeof l1, "MANUAL A%3d B%3d", fanPct[0], fanPct[1]);
  else if (shownState == BLOCKED)  snprintf(l1, sizeof l1, "BLOCKED!chk duct");
  else if (shownState == OFFLINE)  snprintf(l1, sizeof l1, "AI offline");
  else                             snprintf(l1, sizeof l1, "%s", STATE_NAME[shownState]);
  snprintf(l2, sizeof l2, "T%.1f H%.0f P%.0f", lastTemp, lastHum, lastPressure);
  lcd.setCursor(0, 0); lcd.printf("%-16s", l1);
  lcd.setCursor(0, 1); lcd.printf("%-16s", l2);
}

// ---------------- Commands from laptop ----------------
bool parseState(const String &s, State &out) {
  if (s == "NORMAL")  { out = NORMAL;  return true; }
  if (s == "COOKING") { out = COOKING; return true; }
  if (s == "BLOCKED") { out = BLOCKED; return true; }
  return false;
}

void handleLine(String line) {
  line.trim();
  line.toUpperCase();
  if (line.length() == 0) return;

  if (line.startsWith("PREDICTION:")) {
    String p = line.substring(11); p.trim();
    State s;
    if (!parseState(p, s)) { Serial.println("ERR,unknown prediction"); return; }
    lastPredMs = millis();
    everGotPred = true;
    if (s == pendingPred) pendingCount++;
    else { pendingPred = s; pendingCount = 1; }
    if (pendingCount >= PREDICTIONS_TO_SWITCH) aiState = s;
    Serial.printf("ACK,PREDICTION,%s,%d/%d\n", STATE_NAME[s],
                  min(pendingCount, PREDICTIONS_TO_SWITCH), PREDICTIONS_TO_SWITCH);
  } else if (line == "DAMPER OPEN" || line == "DAMPER CLOSE") {
    bool closing = (line == "DAMPER CLOSE");
    setDamper(closing);
    if (!SMALL_FAN_ALWAYS_ON) fanAEnabled = !closing;   // OPEN starts the small fan, CLOSE stops it
    applyFans();              // right away, don't wait for the next 2 s cycle
    Serial.printf("ACK,DAMPER,%s,fanA=%d\n", damperClosed ? "CLOSED" : "OPEN", fanPct[0]);
  } else if (line.startsWith("FAN A ") || line.startsWith("FAN B ")) {
    manualMode = true;
    int ch = line.charAt(4) == 'A' ? 0 : 1;
    setFan(ch, line.substring(6).toInt());
    Serial.printf("ACK,FAN,%c,%d,MANUAL\n", 'A' + ch, fanPct[ch]);
  } else if (line == "MODE AUTO" || line == "MODE MANUAL") {
    manualMode = (line == "MODE MANUAL");
    Serial.printf("ACK,MODE,%s\n", manualMode ? "MANUAL" : "AUTO");
  } else if (line.startsWith("FANHZ ")) {          // debug: change fan PWM frequency live
    uint32_t hz = constrain(line.substring(6).toInt(), 10, 5000);
    bool ok = ledcChangeFrequency(enPin(0), hz, FAN_PWM_BITS) && ledcChangeFrequency(enPin(1), hz, FAN_PWM_BITS);
    for (int ch = 0; ch < 2; ch++) ledcWrite(enPin(ch), map(fanPct[ch], 0, 100, 0, FAN_PWM_MAX));
    Serial.printf(ok ? "ACK,FANHZ,%lu\n" : "ERR,FANHZ %lu failed\n", (unsigned long)hz);
  } else if (line.startsWith("SERVO ") || line.startsWith("SERVO2 ")) {
    // debug: SERVO 1000 (servo 1) / SERVO2 1000 (servo 2) = hold that pulse 2 s
    int i = line.startsWith("SERVO2 ") ? 1 : 0;
    int us = constrain(line.substring(i ? 7 : 6).toInt(), 500, 2500);
    Serial.printf("ACK,SERVO%d,%d us for 2 s\n", i + 1, us);
    servoPulse(SERVOS[i].pin, us);
    delay(2000);
    servoOff(SERVOS[i]);
  } else if (line == "ZERO") {                      // reset pressure "0" to the current value
    zeroPressure();
    Serial.println(pressureOk ? "ACK,ZERO" : "ERR,pressure sensor not found");
  } else if (line == "STATUS") {
    Serial.printf("ACK,STATUS,mode=%s,state=%s,ai=%s,localBlocked=%d,fanA=%d,fanB=%d,damper=%s,damperHold=%d\n",
                  manualMode ? "MANUAL" : "AUTO", STATE_NAME[shownState], STATE_NAME[aiState],
                  localBlocked, fanPct[0], fanPct[1], POS_NAME[damperPos + 1], damperHold);
  } else {
    Serial.println("ERR,unknown command");
  }
}

void readSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (rxLen) { rxBuf[rxLen] = 0; handleLine(String(rxBuf)); rxLen = 0; }
    } else if (rxLen < sizeof(rxBuf) - 1) {
      rxBuf[rxLen++] = c;
    }
  }
}

// ---------------- Setup / loop ----------------
void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(LED_R, OUTPUT); pinMode(LED_Y, OUTPUT); pinMode(LED_G, OUTPUT);
  pinMode(IN2, OUTPUT); digitalWrite(IN2, LOW);
  pinMode(IN4, OUTPUT); digitalWrite(IN4, LOW);
#if FAN_HAS_EN
  pinMode(IN1, OUTPUT); digitalWrite(IN1, HIGH);   // direction fixed, speed on ENA/ENB
  pinMode(IN3, OUTPUT); digitalWrite(IN3, HIGH);
#endif

  // Fixed PWM channels: fans on channels 0+1 (1 kHz), servo on channel 4 (50 Hz).
  // They use different LEDC timers, so the frequencies don't interfere.
  ledcAttachChannel(enPin(0), FAN_PWM_HZ, FAN_PWM_BITS, 0);
  ledcAttachChannel(enPin(1), FAN_PWM_HZ, FAN_PWM_BITS, 1);
  ledcWrite(enPin(0), 0);
  ledcWrite(enPin(1), 0);
  // Servos on channels 4 + 5 (same 50 Hz timer). NOT moved at start-up.
  if (!ledcAttachChannel(SERVO_PIN, 50, 14, 4)) Serial.println("INFO,servo 1 PWM setup failed");
  servoPulse(SERVO_PIN, 0);
  if (USE_SERVO2) {
    if (!ledcAttachChannel(SERVO2_PIN, 50, 14, 5)) Serial.println("INFO,servo 2 PWM setup failed");
    servoPulse(SERVO2_PIN, 0);
  }

  dht.begin();

  // Pressure sensor: zero it now, while the fans are still off.
  pinMode(HX_SCK, OUTPUT);
  digitalWrite(HX_SCK, LOW);
  pinMode(HX_OUT, INPUT_PULLUP);
  delay(200);
  zeroPressure();
  if (!pressureOk) Serial.println("INFO,pressure sensor not found (OUT 18 / SCK 17) - sending nan");

  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.beginTransmission(LCD_ADDR);
  lcdOk = (Wire.endTransmission() == 0);
  if (lcdOk) { lcd.init(); lcd.backlight(); lcd.print("HawkerFlow"); }
  else Serial.println("INFO,LCD not found - check LCD_ADDR (running without LCD)");

#if USE_TACH
  pinMode(TACH_A, INPUT_PULLUP);
  pinMode(TACH_B, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(TACH_A), tachIsrA, FALLING);
  attachInterrupt(digitalPinToInterrupt(TACH_B), tachIsrB, FALLING);
#endif

  Serial.println("HEADER,millis,temp_c,humidity,pressure,fan_a_pct,fan_b_pct,damper_closed,rpm_a,rpm_b,state");
  lastSampleMs = millis();
}

void loop() {
  readSerial();
  updateFans();
  updateLeds();

  unsigned long now = millis();
  if (now - lastSampleMs >= SAMPLE_MS) {
    unsigned long dt = now - lastSampleMs;
    lastSampleMs = now;
    readSensors(dt);
    applyState();
    sendData();
    updateLcd();
  }
}
