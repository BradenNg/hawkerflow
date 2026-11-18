# HawkerFlow – Step-by-Step Setup Guide (Person 2)

Work through the steps in order. **Don't move on until the current step's ✅ check passes.**
Golden rules:
- **Unplug USB and the 12 V battery before changing any wiring.**
- **All grounds connected together** (ESP32 GND, L298 GND, battery −, servo GND).
- **The ESP32 never powers a fan or the servo**: it only sends signals.

Every sketch: open it in Arduino IDE → Board **ESP32S3 Dev Module**, Port **COM6** → Upload →
open Serial Monitor at **115200 baud**, line ending **Newline**.

---

## Step 0 – Get ready (10 min)
1. Check that these libraries show as installed (Library Manager): `DHT sensor library`, `Adafruit Unified Sensor`, `ESP32Servo`, `LiquidCrystal I2C`. (All four are installed already.)
2. On the laptop, run: `pip install pyserial`
3. Read each fan's sticker and write down: **voltage**, **current (A)**, **number of wires**. Measure each fan's size with a ruler.
   → Send the real sizes to Person 3 (mechanical). The brief says 9 cm / 3 cm, but the model numbers suggest ~120 mm and ~50 mm.
4. Find your LCD type: **4 pins** (GND, VCC, SDA, SCL) = I2C, which matches this guide. 16 pins = tell me and we'll change the wiring.

## Step 1 – DHT22 temperature/humidity (already done)
Wiring: `+` → 3V3, `−` → GND, `DATA/OUT` → **GPIO 4**.
Upload `DHT22_Test`.
✅ Prints `OK Temp … Humidity …`. Breathe on it or hold steam near it and **humidity rises**.

## Step 2 – HC-SR04 ultrasonic (blockage sensor)
Wiring:
| HC-SR04 | Goes to |
|---|---|
| VCC | **5V** pin |
| GND | GND |
| TRIG | **GPIO 5** |
| ECHO | **1 kΩ** resistor → **GPIO 6**, and from GPIO 6 a **2 kΩ** resistor → GND |

(No 2 kΩ? Use two 1 kΩ in series. The divider turns ECHO's 5 V into ~3.3 V so the ESP32 pin isn't damaged.)

Upload `HCSR04_Test`.
✅ Prints `OK Distance: xx cm`. Move a hand closer and the number goes down. Point it into the duct, note the **normal reading**, then put a card in the duct and note the **blocked reading**.
→ In `HawkerFlow.ino`, set `BLOCK_DIST_CM` to about halfway between the two readings.

## Step 3 – LCD + traffic-light LEDs
Wiring:
| Part | Pin |
|---|---|
| LCD GND / VCC | GND / **5V** |
| LCD SDA / SCL | **GPIO 8 / GPIO 9** |
| LED module GND | GND |
| LED R / Y / G | **GPIO 16 / 38 / 39** (17/18 are used by the pressure sensor) |

Upload `LcdLedTest`.
✅ Serial shows `OK I2C device at 0x27` (or 0x3F). The LCD shows "HawkerFlow" and the LEDs cycle R→Y→G.
- Blank LCD or only blocks? Turn the small blue screw (contrast) on the back.
- If the address is **not 0x27**, change `LCD_ADDR` in `HawkerFlow.ino`.

## Step 4 – Fans through the L298 (the important one)

### 4a. Know your fan plugs
**3-pin fan plug** (both the 50 mm NMB fans and the 120 mm fan have one):
```
   ┌───────────┐  <- the plastic ridge/tabs are on this side
   │ ■   ■   ■ │
   └───────────┘
     1   2   3
    GND +12V TACH
  black red yellow (NMB fans may use blue/white for TACH)
```
- Pin 1 (black) = **−/GND**, Pin 2 (red, the middle one) = **+12 V**, Pin 3 = **tach (speed signal)**. Leave the tach unconnected for now.
- Always go by the **wire colour**, not the position: red = +, black = −.

**120 mm fan, 4-pin "Molex" plug with only 2 wires.** This is just a second way to power the same fan (a PC power-supply plug). **Don't use it, and don't connect both plugs.** Use the 3-pin plug and leave the Molex hanging (tape it so its metal pins can't touch anything).

### 4b. Get the fan wires into the screw terminals (no cutting needed)
Push a **male jumper wire** pin into each hole of the fan's 3-pin plug (red hole and black hole), then screw the other end of each jumper into the L298 terminal. Tug gently to check they hold, then wrap the plug with tape so the jumpers don't fall out.
For the two small fans on one channel: both **red** jumpers go into the same OUT1 screw, and both **black** jumpers into OUT2. Twist the metal ends together first.

### 4c. L298 board preparation
1. **Pull off the ENA and ENB jumpers** (small black caps on the 2-pin headers next to the 4 IN pins). Keep them somewhere safe.
2. **Keep the "5V-EN" / 12V jumper ON** (near the 3 big power screws). It powers the L298's logic from the 12 V.
3. The big power terminal has 3 screws, usually labelled **+12V | GND | +5V**. Nothing goes on +5V for now (the servo uses it later).

### 4d. Wiring table
| From | To | Wire |
|---|---|---|
| 12 V battery **+** | L298 **+12V** screw | via the 2.1 mm socket adapter (centre pin is usually +; **check with the test pen first**) |
| 12 V battery **−** | L298 **GND** screw | |
| L298 **GND** screw (same screw as battery −) | **ESP32 GND** pin | M-M jumper. **Required**, or nothing works |
| Small fan 1 **red** + small fan 2 **red** | **OUT1** | |
| Small fan 1 **black** + small fan 2 **black** | **OUT2** | |
| 120 mm fan 3-pin **red** | **OUT3** | |
| 120 mm fan 3-pin **black** | **OUT4** | |
| All fans' yellow/blue tach | nothing (tape the hole) | |
| L298 **ENA** signal pin (see below) | **GPIO 10** | F-F jumper |
| L298 **IN1 / IN2** | **GPIO 11 / 12** | F-F jumpers |
| L298 **IN3 / IN4** | **GPIO 14 / 21** | F-F jumpers |
| L298 **ENB** signal pin (see below) | **GPIO 13** | F-F jumper |

Pin order on most L298 boards: **ENA, IN1, IN2, IN3, IN4, ENB** in a row.
**Which ENA/ENB pin?** Under each removed jumper there are 2 pins: one is **5 V** and one is the **EN signal**. Connecting the ESP32 to the 5 V pin can damage it, so check first: connect only the battery (no ESP32 wires yet) and measure each pin against GND with the test pen/multimeter. The pin showing **~5 V is the wrong one**; the pin showing **~0 V is ENA/ENB**. Mark it with a pen.

### 4e. Power-up order
1. Double-check: red to OUT1/OUT3, black to OUT2/OUT4, all grounds joined.
2. Plug in **USB** and upload `FanTest`.
3. **Then** connect the 12 V battery. The fans should stay **off** (the sketch starts at 0%). If a fan spins at full speed immediately, unplug the battery and check that its EN jumper is really removed.
In Serial Monitor type:
1. `A 100`: both small fans spin. ✅
2. `A 0`, then `B 100`: big fan spins. ✅
3. `SWEEP A`, then `SWEEP B`: watch for the % where each fan **stops**. Set `MIN_FAN_PCT` in `HawkerFlow.ino` to ~10 above the higher of the two.

Problems:
- Fan doesn't spin: check red is on OUT1/OUT3 and black on OUT2/OUT4 (these fans only run one way, so reversed wiring = no spin), and that the jumper pins are fully inside the fan plug.
- Nothing at all: check that the ENA/ENB jumpers are removed and the grounds are connected together.
- L298 gets very hot: check the fan current on the sticker (must total < 2 A per channel).

## Step 5 – Servo damper flap (MG90S)
Power for the servo (pick one):
- **Best:** LM2596 buck converter, 12 V in → adjust to **5.0 V** out (check with a multimeter *before* connecting the servo).
- **Fallback:** the L298 board's **+5V** screw terminal (light flap only).

Wiring: servo **brown** → GND, **red** → 5 V supply above, **orange** → **GPIO 15**. Put a **470 µF capacitor** across red/brown (stripe side = GND).

Upload `ServoTest`. Type `OPEN`, `CLOSE`, `ANGLE 45`, etc.
✅ Servo moves smoothly, no buzzing/resetting.
With Person 3, mount the flap in the duct, then use `ANGLE n` to find:
- the angle where the duct is **fully open**, and set it as `DAMPER_OPEN_DEG`
- the angle where it **blocks the duct**, and set it as `DAMPER_CLOSED_DEG`

Put both numbers in `HawkerFlow.ino` (and `ServoTest.ino`).

## Step 6 – Mount everything (with Person 3)
- DHT22: inside the hood near the "cooking" area, not directly in a fan's airflow.
- HC-SR04: pointing **along the duct**, so the damper flap (or any blockage) is in its view.
- Keep the L298 outside the hood (it gets warm). Tape/label every wire.
- Repeat a quick test of Steps 1–5 after mounting.

## Step 7 – Main firmware, manual test
1. Edit the settings block at the top of `HawkerFlow/HawkerFlow.ino` with your numbers from Steps 2–5 (`LCD_ADDR`, `MIN_FAN_PCT`, `DAMPER_*_DEG`, `BLOCK_DIST_CM`).
2. Upload it. You'll see a `HEADER,…` line and then a `DATA,…` line every 2 s.
3. With no laptop AI: after ~10 s the LCD shows **AI offline**, yellow blinks, fans 50%. ✅
4. Type each line **twice** (2 identical predictions are needed to switch):

| Type (twice) | Expected |
|---|---|
| `PREDICTION:NORMAL` | green LED, small fans off, big fan 30%, damper OPEN (90°) |
| `PREDICTION:COOKING` | yellow LED, all fans 100%, damper OPEN |
| `PREDICTION:BLOCKED` | red blinking, LCD "BLOCKED!", big 100%, small 50%, damper slowly turns to RELIEF (120°) |
| `PREDICTION:NORMAL` again | damper slowly returns to OPEN |

5. Type `DAMPER CLOSE`: flap closes and **stays closed** (automatic moves paused). After ~6 s the system goes BLOCKED **by itself** (ultrasonic override). Then `DAMPER OPEN`: flap opens and automatic control resumes. ✅
   Check that the flap at RELIEF is **not** in the HC-SR04's view (otherwise it would stay BLOCKED). If it is, flip the direction: set `DAMPER_RELIEF_DEG` to the other side of `DAMPER_OPEN_DEG`.
6. `FAN A 70`: manual mode. `MODE AUTO`: back to automatic. `STATUS` prints everything.

## Step 8 – Collect training data (with Person 1)
**Close the Serial Monitor first** (only one program can use COM6).
```
cd python
python collect_data.py --port COM6
```
- Type `n` + Enter: room normal, wait ~10 min.
- Type `c`: kettle/hot water steam under the hood, ~10 min.
- Type `b`: damper closes automatically (blocked), ~10 min.
- `p` pauses, `q` quits. Data goes to `python/hawkerflow_data.csv`.

Do 2–3 short sessions per label on different days/times, and give the CSV to Person 1.
**Tell Person 1:** train only on `temp_c`, `humidity`, `distance_cm` (and `rpm_*` if used). Not on `fan_*`, `damper_closed` or `state`.

## Step 9 – Run the AI loop
```
python serial_bridge.py --port COM6
```
- Out of the box it uses simple rules (the first reading is the room baseline): +2 °C or +10 % RH = COOKING, distance below half of normal = BLOCKED.
- Person 1 replaces the `predict()` function with the trained model (instructions are at the top of the file).

✅ Each line shows `T=… RH=… D=… -> PREDICTION (ESP32 state: …)` and the fans react.

## Step 10 – Final test with Person 4 (record results)
| Test | Do | Expect | Record |
|---|---|---|---|
| Normal | Nothing for 2 min | NORMAL, green | readings |
| Cooking | Steam under hood | COOKING within ~10 s, fans 100% | time to react |
| Blocked | `DAMPER CLOSE` or card in duct | BLOCKED, red + LCD warning | time to react |
| AI offline | Stop the Python script | "AI offline" after 10 s | ✔ |
| Heat check | 10 min at full speed | L298/servo/wires only warm | ✔ |

Take photos/videos of each test for the report. Done 🎉
