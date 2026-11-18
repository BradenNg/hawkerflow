"""HawkerFlow data collector (for training the AI model).

Reads DATA lines from the ESP32 (HawkerFlow.ino) and saves them to a CSV
with the label YOU say is happening right now.

Usage (close the Arduino Serial Monitor first!):
    pip install pyserial
    python collect_data.py --port COM6

While it runs, type a key + Enter:
    n  -> label NORMAL   (nothing happening)
    c  -> label COOKING  (kettle / hot water steam under the hood)
    b  -> label BLOCKED  (also closes the damper flap automatically)
    o  -> open the damper again (label stays as it is)
    p  -> pause saving (e.g. while you change the setup)
    q  -> quit
Collect ~10 minutes per label, in a few separate sessions.
"""
import argparse
import csv
import os
import queue
import threading
import time

import serial

LABELS = {"n": "NORMAL", "c": "COOKING", "b": "BLOCKED"}


def keyboard(q):
    while True:
        q.put(input().strip().lower())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="COM6")
    ap.add_argument("--out", default="hawkerflow_data.csv")
    args = ap.parse_args()

    ser = serial.Serial(args.port, 115200, timeout=1)
    time.sleep(2)
    new_file = not os.path.exists(args.out)
    f = open(args.out, "a", newline="")
    w = csv.writer(f)
    if new_file:
        w.writerow(["pc_time", "label", "millis", "temp_c", "humidity", "pressure",
                    "fan_a_pct", "fan_b_pct", "damper_closed", "rpm_a", "rpm_b", "state"])

    keys = queue.Queue()
    threading.Thread(target=keyboard, args=(keys,), daemon=True).start()
    label = None
    saved = 0
    print("Type n / c / b to start labelling, p to pause, q to quit.")

    try:
        while True:
            while not keys.empty():
                k = keys.get()
                if k == "q":
                    return
                if k == "p":
                    label = None
                    print("-- paused --")
                elif k == "o":
                    ser.write(b"DAMPER OPEN\n")
                elif k in LABELS:
                    label = LABELS[k]
                    ser.write(b"DAMPER CLOSE\n" if k == "b" else b"DAMPER OPEN\n")
                    print(f"-- labelling as {label} --")

            line = ser.readline().decode(errors="ignore").strip()
            if not line.startswith("DATA,"):
                if line:
                    print("   ", line)
                continue
            fields = line.split(",")[1:]
            if label is None:
                print("(not saved)", line)
                continue
            w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), label] + fields)
            f.flush()
            saved += 1
            print(f"[{label}] #{saved}", line)
    finally:
        f.close()
        ser.close()
        print(f"Saved {saved} rows to {args.out}")


if __name__ == "__main__":
    main()
