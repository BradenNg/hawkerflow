import numpy as np
import pandas as pd

rng = np.random.default_rng(42)
rows = []

# Synthetic clean-filter pressure differences.
# These are NOT actual HX710B values.
BASELINES = {
    (35, "A"): 2.0,
    (35, "B"): 2.2,
    (100, "A"): 6.0,
    (100, "B"): 6.5
}

for i in range(3000):

    fan = int(rng.choice([35, 100]))
    route = str(rng.choice(["A", "B"]))

    blocked = int(rng.random() < 0.35)

    baseline = BASELINES[(fan, route)]

    # Simulated pressure difference increases
    # with restriction, with overlapping noise.
    if blocked:
        delta = baseline * rng.uniform(1.3, 2.4)
    else:
        delta = baseline * rng.uniform(0.7, 1.4)

    delta += rng.normal(0, 0.25)

    # Simulated pressure readings on active route
    after = 13.0 + rng.normal(0, 0.3)
    before = after + delta

    rows.append({
        "test_id": i,
        "fan_speed": fan,
        "route": route,
        "pressure_before": round(before, 3),
        "pressure_after": round(after, 3),
        "delta_pressure": round(before - after, 3),
        "blocked": blocked
    })

df = pd.DataFrame(rows)

df.to_csv("simulated_data.csv", index=False)

print("Generated 3000 simulated readings!")
print(df.head())
