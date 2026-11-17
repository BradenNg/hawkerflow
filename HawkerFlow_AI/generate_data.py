import numpy as np
import pandas as pd

rng = np.random.default_rng(42)
rows = []

for _ in range(3000):

    cooking = int(rng.random() < 0.5)
    blocked = int(rng.random() < 0.3)

    fan = int(rng.choice([40, 60, 80]))
    route = str(rng.choice(["A", "B"]))

    # Simulate changing ambient temperature
    ambient = rng.uniform(27, 36)

    # Cooking raises temperature, but the
    # increase varies with the situation
    if cooking:
        temperature = ambient + rng.uniform(1, 12)
    else:
        temperature = ambient + rng.uniform(-1, 3)

    # Add measurement variation
    temperature += rng.normal(0, 0.5)

    # Simulate normal airflow
    baseline = (
        1.8 if route == "A" else 1.7
    ) * (fan / 40)

    # Add variation to airflow measurements
    if blocked:
        velocity = baseline * rng.uniform(0.40, 0.90)
    else:
        velocity = baseline * rng.uniform(0.75, 1.10)

    velocity += rng.normal(0, 0.08)
    velocity = max(0, velocity)

    rows.append({
        "temperature": round(temperature, 2),
        "air_velocity": round(velocity, 2),
        "fan_speed": fan,
        "route": route,
        "cooking": cooking,
        "blocked": blocked
    })

df = pd.DataFrame(rows)

df.to_csv("simulated_data.csv", index=False)

print("Generated 3000 more challenging readings!")
print(df.head())

#asdasd