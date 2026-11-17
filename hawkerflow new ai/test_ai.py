import pandas as pd
import joblib
import math

# Load the trained AI models
saved = joblib.load("hawkerflow_ai.joblib")

cooking_model = saved["cooking_model"]
blocked_model = saved["blocked_model"]
columns = saved["columns"]


def test_hawkerflow(temperature, pressure, fan, route):

    # Prepare inputs for AI
    data = pd.DataFrame([{
        "temperature": temperature,
        "pressure": pressure,
        "fan_speed": fan,
        "route": route
    }])

    X = pd.get_dummies(data)
    X = X.reindex(columns=columns, fill_value=0)

    # AI predictions
    cooking = bool(cooking_model.predict(X)[0])
    blocked = bool(blocked_model.predict(X)[0])

    # Simulated control logic
    new_fan = 80 if cooking else 40
    new_route = route

    if blocked:
        new_route = "B" if route == "A" else "A"

    print("\n----------------------------")
    print("Temperature:", temperature, "C")
    print("Pressure:", pressure, "(simulated units)")
    print("Current Fan Speed:", fan, "%")
    print("Current Filter Route:", route)

    print("\nAI PREDICTIONS:")
    print("Cooking Detected:", cooking)
    print("Filter Blocked:", blocked)

    print("\nSIMULATED ACTIONS:")
    print("New Fan Speed:", new_fan, "%")
    print("Proposed Filter Route:", new_route)

    if blocked:
        print("ALERT: Possible filter blockage!")


print("HAWKERFLOW AI V3 TESTING")
print("Simulation only. Pressure is not calibrated.")

while True:
    try:
        temperature = float(input("\nTemperature (C): "))
        pressure = float(input("Pressure (simulated units): "))
        fan = int(input("Fan Speed (40, 60, 80): "))
        route = input("Filter Route (A/B): ").strip().upper()

        if not math.isfinite(temperature) or not math.isfinite(pressure):
            print("Please enter finite sensor values.")
            continue

        if not (-40 <= temperature <= 80):
            print("Temperature outside DHT22 range.")
            continue

        if fan not in [40, 60, 80]:
            print("Choose fan speed 40, 60 or 80.")
            continue

        if route not in ["A", "B"]:
            print("Choose A or B.")
            continue

        test_hawkerflow(
            temperature, pressure, fan, route
        )

    except ValueError:
        print("Invalid input. Please enter valid numbers.")

    again = input("\nTest another scenario? (y/n): ")
    if again.lower().strip() != "y":
        print("HawkerFlow AI testing stopped.")
        break
