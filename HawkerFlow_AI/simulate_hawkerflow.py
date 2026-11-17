import pandas as pd
import joblib

# Loading the AI model trained in Part 1
saved = joblib.load("hawkerflow_ai.joblib")
model = saved["model"]
columns = saved["columns"]

def run_hawkerflow(pm25, air_velocity, fan_speed, route):

    # Prepare sensor data for AI
    data = pd.DataFrame([{
        "pm25": pm25,
        "air_velocity": air_velocity,
        "fan_speed": fan_speed,
        "route": route
    }])

    X = pd.get_dummies(data)
    X = X.reindex(columns=columns, fill_value=0)

    # AI predicts current condition
    condition = model.predict(X)[0]

    # Simple control rules (not trained AI)
    if condition == "Normal":
        new_fan_speed = 40
        new_route = route

    elif condition == "Cooking":
        new_fan_speed = 80
        new_route = route

    elif condition == "Blocked":
        new_fan_speed = fan_speed
        new_route = "B" if route == "A" else "A"

    else:
        new_fan_speed = fan_speed
        new_route = route

    print("\n--- HawkerFlow ---")
    print("PM2.5:", pm25)
    print("Air Velocity:", air_velocity)
    print("AI Prediction:", condition)
    print("Fan Speed:", new_fan_speed, "%")
    print("Filter Route:", new_route)

    if condition == "Blocked":
        print("ALERT: Possible filter blockage!")

# Simulate 3 test scenarios
run_hawkerflow(30, 1.8, 40, "A")


