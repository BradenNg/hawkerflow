"""Try the filter-clog AI by hand: type a fan speed and each vent's pressure drop."""
import joblib
import pandas as pd

THRESHOLD = 0.4

saved = joblib.load("hawkerflow_real_ai.joblib")
if saved.get("type") != "per_vent":
    raise SystemExit("This model is the old format. Run train_real_ai.py first.")
model = saved["model"]


def ask(prompt):
    while True:
        value = input(prompt).strip()
        if value.lower() == "q":
            return None
        try:
            return float(value)
        except ValueError:
            print("Please enter a number (or q).")


print("HAWKERFLOW FILTER-CLOG AI   (q to quit)")
print("Vent A = C - A (pressure_diff3),  vent B = B - A (pressure_diff)")

while True:
    fan = ask("\nFan speed % (35 or 100): ")
    if fan is None:
        break
    for vent in ("A", "B"):
        delta = ask(f"Vent {vent} pressure drop: ")
        if delta is None:
            raise SystemExit
        clogged = bool(model.predict(pd.DataFrame([{"delta": delta, "fan_pct": fan}]))[0])
        print(f"  Vent {vent}:  AI = {'CLOGGED' if clogged else 'clean'}"
              f"   {THRESHOLD} rule = {'CLOGGED' if abs(delta) > THRESHOLD else 'clean'}")
