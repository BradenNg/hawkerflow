
import csv
import math
import os
import sys
import time
import serial

PORT = "COM7"
BAUD_RATE = 115200
SAMPLES_PER_RUN = 30
OUTPUT = "real_pressure_data.csv"

# Order of the values after "DATA," in HawkerFlow.ino
ESP32_COLUMNS = [
    "millis", "temp_c", "humidity",
    "pressure", "pressure2", "pressure3",
    "pressure_diff", "pressure_diff3",
    "fan_a_pct", "fan_b_pct", "damper_closed",
    "rpm_a", "rpm_b", "state"
]

# pressure  = sensor A, pressure2 = sensor B, pressure3 = sensor C
# pressure_diff  = B - A  (vent B)
# pressure_diff3 = C - A  (vent A)
FIELDS = [
    "run_id", "route", "blocked",
    "millis", "temp_c", "pressure",
    "pressure2", "pressure3",
    "pressure_diff", "pressure_diff3",
    "fan_a_pct", "fan_b_pct", "state"
]


def collect(esp32, run_id, route, blocked):
    saved = 0
    speeds = set()
    states = set()

    print("\nCollecting readings...")

    ensure_header()   # in case the CSV was deleted or emptied between runs

    with open(OUTPUT, "a", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)

        while saved < SAMPLES_PER_RUN:
            line = esp32.readline().decode(
                "utf-8", errors="replace"
            ).strip()

            values = next(csv.reader([line]), [])

            if not values or values[0] != "DATA":
                continue
            values = values[1:]

            if len(values) != len(ESP32_COLUMNS):
                print("Skipped row with wrong number of values:", line)
                continue

            data = dict(zip(ESP32_COLUMNS, values))

            try:
                millis = int(data["millis"])
                temp = float(data["temp_c"])
                p1 = float(data["pressure"])
                p2 = float(data["pressure2"])
                p3 = float(data["pressure3"])
                delta = float(data["pressure_diff"])
                delta3 = float(data["pressure_diff3"])
                fan_a = float(data["fan_a_pct"])
                fan_b = float(data["fan_b_pct"])
                state = data["state"]
            except ValueError:
                continue

            readings = {"temp": temp, "A": p1, "B": p2, "C": p3}
            missing = [k for k, x in readings.items() if math.isnan(x)]
            if missing:
                print("Skipped (no reading from:", ", ".join(missing) + ")")
                continue
            if not all(abs(x) < 100000 for x in readings.values()):
                continue

            speeds.add((fan_a, fan_b))
            states.add(state)

            writer.writerow({
                "run_id": run_id,
                "route": route,
                "blocked": blocked,
                "millis": millis,
                "temp_c": temp,
                "pressure": p1,
                "pressure2": p2,
                "pressure3": p3,
                "pressure_diff": delta,
                "pressure_diff3": delta3,
                "fan_a_pct": fan_a,
                "fan_b_pct": fan_b,
                "state": state
            })

            saved += 1
            print(
                f"{saved}/{SAMPLES_PER_RUN} "
                f"B-A (vent B): {delta}   C-A (vent A): {delta3}"
            )

    print("Run saved!")
    print("Reported fan settings:", speeds)
    print("Reported states:", states)
    print("Check that the actual fan and route")
    print("were stable throughout this run.")


def ensure_header():
    """Make sure the CSV starts with the standard FIELDS header.

    - No file / empty file: create it with the header.
    - Header already correct: nothing to do.
    - Data in the current layout but no header: add the header on top,
      keeping every row.
    - Data in another layout (e.g. old file without sensor C): stop,
      so the two layouts never get mixed.
    """
    if not os.path.exists(OUTPUT) or os.path.getsize(OUTPUT) == 0:
        with open(OUTPUT, "w", newline="") as file:
            csv.writer(file).writerow(FIELDS)
        print(f"Created {OUTPUT} with header.")
        return

    with open(OUTPUT, newline="") as file:
        rows = [row for row in csv.reader(file) if row]

    if rows and rows[0] == FIELDS:
        return

    # Drop any other header line (e.g. the old layout's header with no data).
    data_rows = [row for row in rows if row[0] != "run_id"]

    if all(len(row) == len(FIELDS) for row in data_rows):
        with open(OUTPUT, "w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(FIELDS)
            writer.writerows(data_rows)
        print(f"Added the header to {OUTPUT} ({len(data_rows)} rows kept).")
        return

    print(f"{OUTPUT} has rows in a different column layout "
          f"(expected {len(FIELDS)} columns).")
    print("Rename or move it, then run this again.")
    sys.exit(1)


def main():
    ensure_header()

    with serial.Serial(
        PORT, BAUD_RATE, timeout=2
    ) as esp32:
        time.sleep(2)
        esp32.reset_input_buffer()

        print("Connected to ESP32!")

        while True:
            route = input(
                "\nVent whose filter is being tested (A/B): "
            ).strip().upper()

            if route not in ("A", "B"):
                print("Enter A or B.")
                continue

            choice = input(
                "Filter condition (0=clean, 1=blocked): "
            ).strip()

            if choice not in ("0", "1"):
                print("Enter 0 or 1.")
                continue

            run_id = input(
                "Unique run ID (e.g. A_clean_1): "
            ).strip()

            if not run_id:
                print("Run ID cannot be empty.")
                continue

            input(
                "Stabilise fan and filter, "
                "then press Enter to record..."
            )

            esp32.reset_input_buffer()

            collect(
                esp32, run_id, route, int(choice)
            )

            again = input(
                "\nCollect another run? (y/n): "
            ).lower()

            if again != "y":
                break


try:
    main()
except KeyboardInterrupt:
    print("\nStopped.")
except serial.SerialException as error:
    print("Serial error:", error)
