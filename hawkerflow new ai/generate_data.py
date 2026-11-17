import numpy as np
import pandas as pd

# Make random results reproducible
rng = np.random.default_rng(42)

rows = []

# Generate 3000 simulated readings
for _ in range(3000):

    # Simulate whether cooking is happening
    cooking = int(rng.random() < 0.5)

    # Simulate whether filter is blocked
    blocked = int(rng.random() < 0.3)

    # Fan speed and filter route
    fan = int(rng.choice([40, 60, 80]))
    route = str(rng.choice(["A", "B"]))

    # DHT22 temperature simulation
    ambient = rng.uniform(27, 36)

    if cooking:
        temperature = ambient + rng.uniform(1, 12)
    else:
        temperature = ambient + rng.uniform(-1, 3)

    temperature += rng.normal(0, 0.5)

    # HX710B pressure simulation
    # Arbitrary relative pressure units.
    # NOT real Pa or calibrated HX710B readings.

    baseline = (
        1000 if route == "A" else 950
    ) * (fan / 40)

    # Fictional assumption:
    # blockage tends to increase this reading.
    if blocked:
        pressure = baseline * rng.uniform(1.15, 1.75)
    else:
        pressure = baseline * rng.uniform(0.85, 1.25)

    pressure += rng.normal(0, 60)

    # Save one reading
    rows.append({
        "temperature": round(temperature, 2),
        "pressure": round(pressure, 2),
        "fan_speed": fan,
        "route": route,
        "cooking": cooking,
        "blocked": blocked
    })

# Convert into a table
df = pd.DataFrame(rows)

# Save data into CSV file
df.to_csv("simulated_data.csv", index=False)

print("Successfully generated 3000 readings!")
print(df.head())
