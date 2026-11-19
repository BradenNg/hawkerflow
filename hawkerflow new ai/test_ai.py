
import pandas as pd
import joblib
import math

saved = joblib.load("hawkerflow_ai.joblib")

model = saved["model"]
columns = saved["columns"]


def get_fan_speed(temperature):
    if temperature < 33:
        return 0
    elif temperature <= 39:
        return 35
    else:
        return 100


def predict_blockage(delta, fan, route):

    data = pd.DataFrame([{
        "delta_pressure": delta,
        "fan_speed": fan,
        "route": route
    }])

    X = pd.get_dummies(data)
    X = X.reindex(columns=columns, fill_value=0)

    return bool(model.predict(X)[0])


def test_hawkerflow(temp, p1, p2, p3, p4, route):

    fan = get_fan_speed(temp)

    # Pressure difference for both routes
    delta_a = p1 - p2
    delta_b = p3 - p4

    print("\n----------------------------")
    print("Temperature:", temp, "C")
    print("Fan speed:", fan, "%")
    print("Active route:", route)

    print("\nPRESSURE READINGS:")
    print("Route A difference:", round(delta_a, 3))
    print("Route B difference:", round(delta_b, 3))

    if fan == 0:
        print("\nFan OFF")
        print("Blockage check skipped.")
        print("No route switching required.")
        return

    # Only classify the active route
    delta = delta_a if route == "A" else delta_b

    blocked = predict_blockage(delta, fan, route)

    print("\nAI PREDICTION:")
    print("Active filter blocked:", blocked)

    if blocked:
        proposed_route = "B" if route == "A" else "A"

        print("\nPOSSIBLE BLOCKAGE!")
        print("Proposed route:", proposed_route)
        print("ALERT: Inspect Filter", route)
        print("Confirm alternate route is clear")
        print("before commanding servo.")
    else:
        print("\nFilter appears normal.")
        print("Keep route:", route)


print("HAWKERFLOW FINAL AI TESTING")
print("Synthetic pressure simulation only.")

while True:
    try:
        temp = float(input("\nTemperature (C): "))

        p1 = float(input("Pressure P1 (Before A): "))
        p2 = float(input("Pressure P2 (After A): "))
        p3 = float(input("Pressure P3 (Before B): "))
        p4 = float(input("Pressure P4 (After B): "))

        route = input("Active route (A/B): ").strip().upper()

        values = [temp, p1, p2, p3, p4]

        if not all(math.isfinite(x) for x in values):
            print("Invalid sensor readings.")
            continue

        if not (-40 <= temp <= 80):
            print("Temperature outside DHT22 range.")
            continue

        if route not in ["A", "B"]:
            print("Choose route A or B.")
            continue

        test_hawkerflow(temp, p1, p2, p3, p4, route)

    except ValueError:
        print("Please enter valid numbers.")
        continue

    again = input("\nTest again? (y/n): ")
    if again.strip().lower() != "y":
        break
