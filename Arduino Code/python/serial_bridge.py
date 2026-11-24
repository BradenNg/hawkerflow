"""HawkerFlow serial bridge: ESP32 <-> AI model.

ESP32 sends:   DATA,millis,temp_c,humidity,pressure,pressure2,pressure3,pressure_diff,pressure_diff3,fan_a_pct,fan_b_pct,damper_closed,rpm_a,rpm_b,state
We reply:      PREDICTION:NORMAL | PREDICTION:COOKING | PREDICTION:BLOCKED

Usage (close the Arduino Serial Monitor first!):
    pip install pyserial
    python serial_bridge.py --port COM6

Person 1: replace the body of predict() with the trained model, e.g.
    model = joblib.load("model.pkl")
    return model.predict([[f["temp_c"], f["humidity"], f["pressure"]]])[0]
Only use sensor inputs (temp_c, humidity, pressure*, pressure_diff*, rpm_*) - NOT fan_*,
damper_closed or state, which are outputs of the system.
"""
import argparse
import math
import time

import serial

FIELDS = ["millis", "temp_c", "humidity", "pressure", "pressure2", "pressure3",
          "pressure_diff", "pressure_diff3", "fan_a_pct", "fan_b_pct",
          "damper_closed", "rpm_a", "rpm_b", "state"]

# --- simple rule-based stand-in until the AI model is ready ---
baseline = {}


PRESSURE_BLOCKED = 50.0   # |pressure| above this = blocked duct (tune after the duct test)


def predict(f):
    t, h = f["temp_c"], f["humidity"]
    pressures = [p for p in (f["pressure"], f["pressure2"], f["pressure3"]) if not math.isnan(p)]
    if math.isnan(t) or math.isnan(h):
        return "NORMAL"
    if "t" not in baseline:              # first reading = room conditions
        baseline.update(t=t, h=h)
        print(f"Baseline: T={t} RH={h}")
    if any(abs(p) > PRESSURE_BLOCKED for p in pressures):
        return "BLOCKED"
    if t > baseline["t"] + 2.0 or h > baseline["h"] + 10.0:
        return "COOKING"
    return "NORMAL"


def parse(line):
    parts = line.split(",")[1:]
    if len(parts) != len(FIELDS):
        return None
    f = {}
    for name, val in zip(FIELDS, parts):
        if name == "state":
            f[name] = val
        else:
            try:
                f[name] = float(val)
            except ValueError:
                f[name] = float("nan")
    return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="COM6")
    args = ap.parse_args()

    ser = serial.Serial(args.port, 115200, timeout=1)
    time.sleep(2)
    ser.write(b"ZERO\n")       # current pressure = 0 (keep the tube still, not pinched)
    print("Pressure re-zeroed. Bridge running. Ctrl+C to stop.")
    try:
        while True:
            line = ser.readline().decode(errors="ignore").strip()
            if not line:
                continue
            if not line.startswith("DATA,"):
                print("   ESP32:", line)
                continue
            f = parse(line)
            if f is None:
                print("   bad DATA line:", line)
                continue
            pred = predict(f)
            ser.write(f"PREDICTION:{pred}\n".encode())
            print(f"T={f['temp_c']:.1f} RH={f['humidity']:.1f} "
                  f"P1={f['pressure']:.1f} P2={f['pressure2']:.1f} P3={f['pressure3']:.1f} "
                  f"B-A={f['pressure_diff']:.1f} C-A={f['pressure_diff3']:.1f} "
                  f"-> {pred}   (ESP32 state: {f['state']})")
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()


if __name__ == "__main__":
    main()
