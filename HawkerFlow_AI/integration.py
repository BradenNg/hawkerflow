
import pandas as pd
import joblib
import math

# Load updated DHT22-based AI models
saved = joblib.load("hawkerflow_ai_v2.joblib")

cooking_model = saved["cooking_model"]
blocked_model = saved["blocked_model"]
columns = saved["columns"]


def process_sensor_data(message):

    # Expected ESP32 message:
    # TEMP:43.0,VELOCITY:0.6,FAN:40,ROUTE:A

    try:
        values = dict(
            item.strip().split(":", 1)
            for item in message.strip().split(",")
        )

        temperature = float(values["TEMP"])
        velocity = float(values["VELOCITY"])
        fan = int(values["FAN"])
        route = values["ROUTE"].strip().upper()

        # Basic validation
        if not all(math.isfinite(x) for x in [temperature, velocity]):
            raise ValueError("Invalid sensor reading")

        if temperature < -40 or temperature > 80:
            raise ValueError("Temperature outside DHT22 range")

        if velocity < 0:
            raise ValueError("Negative air velocity")

        if fan not in [40, 60, 80]:
            raise ValueError("Invalid fan speed")

        if route not in ["A", "B"]:
            raise ValueError("Invalid filter route")

        # Prepare AI inputs
        data = pd.DataFrame([{
            "temperature": temperature,
            "air_velocity": velocity,
            "fan_speed": fan,
            "route": route
        }])

        X = pd.get_dummies(data)
        X = X.reindex(columns=columns, fill_value=0)

        # Run AI predictions
        cooking = bool(cooking_model.predict(X)[0])
        blocked = bool(blocked_model.predict(X)[0])

        # Simulated control decisions
        new_fan = 80 if cooking else 40
        new_route = route

        if blocked:
            new_route = "B" if route == "A" else "A"

        command = f"FAN:{new_fan},ROUTE:{new_route}"

        # Show results
        print("\n----------------------------")
        print("Received:", message)
        print("Cooking Detected:", cooking)
        print("Filter Blocked:", blocked)
        print("Command:", command)

        if blocked:
            print("ALERT: Possible filter blockage!")

        return command

    except (ValueError, KeyError) as error:
        print("Invalid sensor message:", error)
        return None


# Test messages simulating ESP32 readings
test_messages = [
    "TEMP:29,VELOCITY:1.8,FAN:40,ROUTE:A",
    "TEMP:43,VELOCITY:1.8,FAN:40,ROUTE:A",
    "TEMP:29,VELOCITY:0.6,FAN:40,ROUTE:A",
    "TEMP:43,VELOCITY:0.6,FAN:40,ROUTE:A"
]

for message in test_messages:
    process_sensor_data(message)
