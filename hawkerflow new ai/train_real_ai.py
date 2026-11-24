"""Train the HawkerFlow filter-clog AI from real_pressure_data.csv.

Layout of the duct:
    sensor A (before the filters) --+--> filter A --> sensor C   (vent A)
                                    +--> filter B --> sensor B   (vent B)

The model judges ONE vent at a time from:
    delta   = pressure drop across that vent's filter
              vent A: pressure_diff3 (C - A),  vent B: pressure_diff (B - A)
    fan_pct = fan speed (the drop is bigger at higher fan speed)

Every collected row gives two examples: the vent that was being tested
("route" column) with the run's clean/blocked label, and the other vent,
which is assumed clean during that run.
"""
import joblib
import pandas as pd
from sklearn.metrics import accuracy_score, classification_report
from sklearn.tree import DecisionTreeClassifier, export_text

DATA_FILE = "real_pressure_data.csv"
MODEL_FILE = "hawkerflow_real_ai.joblib"

VENT_DELTA = {"A": "pressure_diff3", "B": "pressure_diff"}
FEATURES = ["delta", "fan_pct"]
THRESHOLD = 0.4          # the team's fixed rule, for comparison


def per_vent(rows):
    """One row per vent per reading."""
    parts = []
    for vent, column in VENT_DELTA.items():
        part = pd.DataFrame({
            "run_id": rows["run_id"],
            "vent": vent,
            "delta": rows[column],
            "fan_pct": rows["fan_b_pct"],
            # blocked only if this vent's filter was the one being tested
            "blocked": ((rows["route"] == vent) & (rows["blocked"] == 1)).astype(int),
        })
        parts.append(part)
    return pd.concat(parts, ignore_index=True).dropna(subset=FEATURES)


data = pd.read_csv(DATA_FILE)
needed = ["run_id", "route", "blocked", "fan_b_pct", *VENT_DELTA.values()]
missing = [c for c in needed if c not in data.columns]
if missing:
    raise ValueError(f"{DATA_FILE} is missing columns {missing}. "
                     "Collect data with the 3-sensor collect_data.py.")

data["blocked"] = data["blocked"].astype(int)
data["route"] = data["route"].str.upper()

print("Runs in the data:")
print(data.groupby("run_id", sort=False)
          .agg(vent=("route", "first"), blocked=("blocked", "first"),
               fan=("fan_b_pct", "first"), rows=("blocked", "size"))
          .to_string())

samples = per_vent(data)

# Hold out whole runs: the last clean run and the last blocked run.
clean_runs = sorted(data.loc[data["blocked"] == 0, "run_id"].unique())
blocked_runs = sorted(data.loc[data["blocked"] == 1, "run_id"].unique())
if len(clean_runs) < 2 or len(blocked_runs) < 2:
    raise ValueError("Need at least 2 clean runs and 2 blocked runs.")
test_runs = {clean_runs[-1], blocked_runs[-1]}

train = samples[~samples["run_id"].isin(test_runs)]
test = samples[samples["run_id"].isin(test_runs)]

model = DecisionTreeClassifier(max_depth=3, min_samples_leaf=5, random_state=42)
model.fit(train[FEATURES], train["blocked"])
pred = model.predict(test[FEATURES])

print(f"\nHELD-OUT TEST (runs {', '.join(sorted(test_runs))})")
print("AI accuracy:", round(accuracy_score(test["blocked"], pred), 3))
print(classification_report(test["blocked"], pred, labels=[0, 1],
                            target_names=["Clean", "Clogged"], zero_division=0))
baseline = (test["delta"].abs() > THRESHOLD).astype(int)   # size, either sign
print(f"{THRESHOLD} rule accuracy:", round(accuracy_score(test["blocked"], baseline), 3))

# Final model on all the data
final = DecisionTreeClassifier(max_depth=3, min_samples_leaf=5, random_state=42)
final.fit(samples[FEATURES], samples["blocked"])
print("\nRules learned:")
print(export_text(final, feature_names=FEATURES))

joblib.dump({
    "type": "per_vent",
    "model": final,
    "features": FEATURES,
    "vent_delta": VENT_DELTA,
}, MODEL_FILE)
print(f"Saved {MODEL_FILE}")
