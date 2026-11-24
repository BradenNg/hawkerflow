"""HawkerFlow live integration: ESP32 <-> laptop AI.

Duct layout:
    sensor A (before the filters) --+--> filter A --> sensor C   (vent A, servo 1)
                                    +--> filter B --> sensor B   (vent B, servo 2)

Every DATA line from the ESP32 (every 2 s):
  1. COOKING CHECK (DHT22 temperature)
        below 33 C  -> not cooking, fan OFF       -> state NORMAL
        33 - 39 C   -> cooking,     fan 35%       -> state COOKING
        above 39 C  -> cooking,     fan 100%      -> state COOKING
     sent to the ESP32 as  SPEED <pct>
  2. FILTER CHECK (only while the fan is running steadily)
        pressure drop across each filter:  vent A = C - A,  vent B = B - A
        the AI (hawkerflow_real_ai.joblib) decides per vent: over the limit or not
  3. VENT CONTROL
        - after every ESP32 reset both vents start OPEN (the firmware opens them)
        - over the limit CONFIRM_READS times in a row  -> vent CLOSES + WARNING here
        - closed for at least MIN_CLOSED_S, then below the limit
          REOPEN_READS times in a row                  -> vent OPENS again
        - never closes the last open vent (the kitchen still needs exhaust)
     Type A or B + Enter to force a vent open.

Run:  python live_integration.py        (close the Arduino Serial Monitor first)
"""
import csv
import math
import queue
import threading
import time

import joblib
import pandas as pd
import serial

from integration import PRESSURE_LIMIT, get_fan_speed

PORT = "COM7"
BAUD_RATE = 115200
MODEL_FILE = "hawkerflow_real_ai.joblib"
CONFIRM_READS = 3       # over the limit this many readings in a row -> close (3 x 2 s = 6 s)
REOPEN_READS = 3        # below the limit this many readings in a row -> open again
MIN_CLOSED_S = 20       # a closed vent stays closed at least this long before it can reopen.
                        # Needed because with the vent closed, almost no air goes through
                        # its filter, so its pressure drop falls even if the filter is dirty.

# Order of the values after "DATA," in HawkerFlow.ino
COLUMNS = [
    "millis", "temp_c", "humidity",
    "pressure", "pressure2", "pressure3",
    "pressure_diff", "pressure_diff3",
    "fan_a_pct", "fan_b_pct", "damper_closed",
    "rpm_a", "rpm_b", "state"
]
VENTS = ("A", "B")
VENT_BIT = {"A": 1, "B": 2}                                   # damper_closed bits
VENT_DELTA = {"A": "pressure_diff3", "B": "pressure_diff"}   # C - A, B - A

# ---------------- AI model ----------------
try:
    saved = joblib.load(MODEL_FILE)
except FileNotFoundError:
    saved = {}
if saved.get("type") == "per_vent":
    model = saved["model"]
    VENT_DELTA = saved.get("vent_delta", VENT_DELTA)
    print("AI model loaded:", MODEL_FILE)
else:
    model = None
    print(f"No per-vent AI model found - run train_real_ai.py. "
          f"Using the {PRESSURE_LIMIT} rule for now.")


def over_limit(delta, fan_pct):
    """AI decision for one vent (falls back to the fixed rule). Returns (ai, rule)."""
    rule = abs(delta) > PRESSURE_LIMIT     # size of the difference, either sign
    if model is None:
        return rule, rule
    ai = bool(model.predict(pd.DataFrame([{"delta": delta, "fan_pct": fan_pct}]))[0])
    return ai, rule


# ---------------- State ----------------
last_fan = None
last_millis = None
over_streak = {v: 0 for v in VENTS}     # readings over the limit in a row
under_streak = {v: 0 for v in VENTS}    # readings below the limit in a row (closed vent)
clogged = {v: False for v in VENTS}     # alert is on
closed = {v: False for v in VENTS}      # vent closed (as reported by the ESP32)
closed_at = {v: 0.0 for v in VENTS}


def warn(text):
    bar = "!" * 60
    print(f"\a\n{bar}\n  WARNING: {text}\n{bar}")


def reset_state():
    for v in VENTS:
        over_streak[v] = under_streak[v] = 0
        clogged[v] = closed[v] = False


def parse(line):
    values = next(csv.reader([line]), [])
    if not values or values[0].strip().upper() != "DATA":
        return None
    values = values[1:]
    if len(values) != len(COLUMNS):
        print("Skipped unexpected row (", len(values), "values) - is the latest HawkerFlow.ino uploaded?")
        return None
    data = dict(zip(COLUMNS, values))
    for name in COLUMNS:
        if name != "state":
            try:
                data[name] = float(data[name])
            except ValueError:
                data[name] = float("nan")
    return data


def close_vent(v, esp32):
    esp32.write(f"VENT {v} CLOSE\n".encode())
    closed[v] = True
    closed_at[v] = time.time()
    under_streak[v] = 0


def open_vent(v, esp32):
    esp32.write(f"VENT {v} OPEN\n".encode())
    closed[v] = clogged[v] = False
    over_streak[v] = under_streak[v] = 0


def process(data, esp32):
    global last_fan, last_millis

    # ESP32 reset? (its clock starts again) -> it has opened both vents
    if last_millis is not None and data["millis"] < last_millis:
        print("\nESP32 restarted - both vents are open again, starting fresh.")
        reset_state()
    last_millis = data["millis"]

    # The ESP32 reports which vents are really closed
    if math.isfinite(data["damper_closed"]):
        mask = int(data["damper_closed"])
        for v in VENTS:
            is_closed = bool(mask & VENT_BIT[v])
            if is_closed and not closed[v]:
                closed_at[v] = time.time()
            closed[v] = is_closed

    temp = data["temp_c"]
    current_fan = data["fan_b_pct"]

    # 1. Cooking check -> fan speed (keep the last speed if the DHT22 failed)
    if math.isfinite(temp):
        new_fan = get_fan_speed(temp)
    else:
        new_fan = last_fan if last_fan is not None else 0
    esp32.write(f"SPEED {new_fan}\n".encode())     # re-sent every cycle (keep-alive)
    last_fan = new_fan
    cooking = new_fan > 0

    # 2 + 3. Filter check and vent control, per vent (needs steady airflow)
    steady = cooking and current_fan == new_fan
    report = {}
    for v in VENTS:
        delta = data[VENT_DELTA[v]]
        where = "CLOSED" if closed[v] else "open"
        if not steady:
            report[v] = f"{where}  drop {delta}  (not checked: fan {'off' if not cooking else 'changing'})"
            continue
        if not math.isfinite(delta):
            report[v] = f"{where}  no reading (sensor missing)"
            continue

        ai, rule = over_limit(delta, new_fan)
        verdict = (f"drop {delta:+.1f}  AI: {'OVER' if ai else 'ok'}"
                   f"  ({PRESSURE_LIMIT} rule: {'OVER' if rule else 'ok'})")
        other = "B" if v == "A" else "A"

        if not closed[v]:
            over_streak[v] = over_streak[v] + 1 if ai else 0
            if not ai and clogged[v]:          # was kept open for safety, now fine
                clogged[v] = False
            report[v] = f"open    {verdict}" + (f"  [{over_streak[v]}/{CONFIRM_READS}]" if ai else "")
            if over_streak[v] >= CONFIRM_READS and not clogged[v]:
                clogged[v] = True
                if closed[other]:
                    warn(f"FILTER {v} IS CLOGGED, and vent {other} is already closed.\n"
                         f"  Vent {v} is kept OPEN so the kitchen still has exhaust.\n"
                         f"  Change BOTH filters now!")
                else:
                    close_vent(v, esp32)
                    warn(f"FILTER {v} IS CLOGGED - vent {v} has been CLOSED.\n"
                         f"  Air now goes through vent {other}. Please change filter {v}.\n"
                         f"  The vent reopens by itself once its pressure is back below the limit.")
        else:
            under_streak[v] = 0 if ai else under_streak[v] + 1
            waited = time.time() - closed_at[v]
            report[v] = f"CLOSED  {verdict}"
            if waited < MIN_CLOSED_S:
                report[v] += f"  [can reopen in {MIN_CLOSED_S - waited:.0f} s]"
            elif not ai:
                report[v] += f"  [below limit {under_streak[v]}/{REOPEN_READS}]"
            if waited >= MIN_CLOSED_S and under_streak[v] >= REOPEN_READS:
                open_vent(v, esp32)
                print(f"\n>>> Vent {v}: pressure back below the limit - vent {v} OPENED again.")
                report[v] += "  -> OPENED"
                if clogged[other] and not closed[other]:   # other one was kept open for safety
                    close_vent(other, esp32)
                    warn(f"Vent {v} is open again, so clogged vent {other} is now CLOSED.")

    # State for the ESP32 LEDs / LCD
    if any(clogged.values()):
        state = "BLOCKED"
    elif cooking:
        state = "COOKING"
    else:
        state = "NORMAL"
    esp32.write(f"PREDICTION:{state}\n".encode())

    print("\n----------------------------")
    print(f"Temperature: {temp} C  -> {'COOKING' if cooking else 'not cooking'}, "
          f"fan {new_fan}% (now {current_fan:.0f}%)")
    for v in VENTS:
        print(f"  Vent {v}: {report[v]}")
    print(f"State: {state}")
    for v in VENTS:
        if clogged[v]:
            print(f"  >> ALERT: filter {v} clogged - please change it")


def keyboard(keys):
    while True:
        keys.put(input().strip().upper())


def main():
    with serial.Serial(PORT, BAUD_RATE, timeout=2) as esp32:
        time.sleep(2)
        esp32.reset_input_buffer()
        for v in VENTS:                       # start with both vents open
            esp32.write(f"VENT {v} OPEN\n".encode())
        print("Connected to ESP32! Ctrl+C to stop.")
        print("Vents close and reopen automatically. Type A or B + Enter to force a vent open.")
        print("Waiting for the first DATA line (the ESP32 may restart and zero the sensors first)...")

        keys = queue.Queue()
        threading.Thread(target=keyboard, args=(keys,), daemon=True).start()

        last_line = time.time()
        warned = False
        while True:
            while not keys.empty():
                k = keys.get()
                if k in VENTS:
                    open_vent(k, esp32)
                    print(f"\nVent {k} opened by hand.")
                elif k:
                    print("Type A or B to force a vent open.")

            line = esp32.readline().decode("utf-8", errors="replace").strip()
            if not line:
                if not warned and time.time() - last_line > 10:
                    warned = True
                    print(f"\nNo data from the ESP32 on {PORT} for 10 s. Check:")
                    print("  - Open the Arduino Serial Monitor: DATA lines every 2 s? (close it after)")
                    print("  - Tools > USB CDC On Boot must be Disabled when uploading.")
                    print("  - Is the cable in the same port that collect_data.py used?")
                    print("  - Press the RST button on the board.")
                continue
            if warned:
                print("ESP32 is sending again.")
            last_line = time.time()
            warned = False

            data = parse(line)
            if data is not None:
                process(data, esp32)
            elif line.startswith("ERR"):
                print("   ESP32:", line, "  <- is the latest HawkerFlow.ino uploaded?")
            elif not line.startswith(("ACK,SPEED", "ACK,PREDICTION", "ACK,VENT")):
                print("   ESP32:", line)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
    except serial.SerialException as error:
        print("Serial connection error:", error)
