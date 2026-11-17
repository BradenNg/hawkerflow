
import pandas as pd
import joblib

# Load temperature-based AI models
saved = joblib.load("hawkerflow_ai_v2.joblib")

cooking_model = saved["cooking_model"]
blocked_model = saved["blocked_model"]
columns = saved["columns"]


def test_hawkerflow(temperature, velocity, fan, route):

    data = pd.DataFrame([{
        "temperature": temperature,
        "air_velocity": velocity,
        "fan_speed": fan,
        "route": route
    }])

    X = pd.get_dummies(data)
    X = X.reindex(columns=columns, fill_value=0)

    # AI predictions
    cooking = bool(cooking_model.predict(X)[0])
    blocked = bool(blocked_model.predict(X)[0])

    # Simulated control decisions
    new_fan = 80 if cooking else 40
    new_route = route

    if blocked:
        new_route = "B" if route == "A" else "A"

    print("\n----------------------------")
    print("Temperature:", temperature, "C")
    print("Air Velocity:", velocity, "m/s")
    print("Current Fan Speed:", fan, "%")
    print("Current Route:", route)

    print("\nAI PREDICTIONS:")
    print("Cooking Detected:", cooking)
    print("Filter Blocked:", blocked)

    print("\nSIMULATED ACTIONS:")
    print("New Fan Speed:", new_fan, "%")
    print("New Filter Route:", new_route)

    if blocked:
        print("ALERT: Possible filter blockage!")


print("HAWKERFLOW DHT22 AI TESTING")

while True:
    try:
        temperature = float(input("\nTemperature (C): "))
        velocity = float(input("Air velocity (m/s): "))
        fan = int(input("Fan speed (40, 60, 80): "))
        route = input("Filter route (A/B): ").upper().strip()

        if not (0 <= temperature <= 80):
            print("Temperature outside practice range.")
            continue

        if velocity < 0:
            print("Air velocity cannot be negative.")
            continue

        if fan not in [40, 60, 80]:
            print("Choose 40, 60 or 80.")
            continue

        if route not in ["A", "B"]:
            print("Choose route A or B.")
            continue

        test_hawkerflow(temperature, velocity, fan, route)

    except ValueError:
        print("Invalid input. Please enter valid numbers.")

    again = input("\nTest another scenario? (y/n): ")
    if again.lower().strip() != "y":
        break
