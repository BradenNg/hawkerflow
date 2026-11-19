import math

# Final HawkerFlow settings
PRESSURE_LIMIT = 0.4


def get_fan_speed(temperature):
    if temperature < 33:
        return 0
    elif temperature <= 39:
        return 35
    else:
        return 100


def process_sensor_data(message):
    try:
        # Expected input:
        # TEMP:36,DELTA_A:0.2,DELTA_B:0.3,FAN:35,ROUTE:A

        values = dict(
            item.strip().split(":", 1)
            for item in message.strip().split(",")
        )

        temp = float(values["TEMP"])
        delta_a = float(values["DELTA_A"])
        delta_b = float(values["DELTA_B"])

        current_fan = int(values["FAN"])
        route = values["ROUTE"].strip().upper()

        if not all(math.isfinite(x) for x in
                   [temp, delta_a, delta_b]):
            raise ValueError("Invalid sensor value")

        if not -40 <= temp <= 80:
            raise ValueError("Invalid temperature")

        if current_fan not in [0, 35, 100]:
            raise ValueError("Invalid fan setting")

        if route not in ["A", "B"]:
            raise ValueError("Invalid route")

        # Temperature-based fan control
        new_fan = get_fan_speed(temp)

        # Choose active filter pressure difference
        active_delta = (
            delta_a if route == "A" else delta_b
        )

        blocked = None
        proposed_route = route

        # Blockage detection is currently
        # validated only for 35% fan speed.
        if new_fan == 35 and current_fan == 35:

            if active_delta >= 0:
                blocked = active_delta > PRESSURE_LIMIT

                if blocked:
                    proposed_route = (
                        "B" if route == "A" else "A"
                    )

        print("\n----------------------------")
        print("Temperature:", temp, "C")
        print("Requested fan speed:", new_fan, "%")
        print("Current fan speed:", current_fan, "%")

        print("\nPRESSURE DIFFERENCES:")
        print("Route A:", delta_a)
        print("Route B:", delta_b)
        print("Active route:", route)

        print("\nFILTER STATUS:")

        if blocked is True:
            print("POSSIBLE BLOCKAGE!")
            print("Inspect Filter", route)
            print("Proposed route:", proposed_route)
            print("ALERT: Maintenance required!")

        elif blocked is False:
            print("Filter appears unclogged.")

        else:
            print("Blockage check skipped.")
            print("Requires stable fan at 35%.")

        # Preserve current route until
        # alternative route is verified.
        command = f"FAN:{new_fan},ROUTE:{route}"

        print("\nPROPOSED COMMAND:")
        print(command)

        return command

    except (ValueError, KeyError) as error:
        print("Invalid sensor data:", error)
        return None


if __name__ == "__main__":

    test_messages = [
        "TEMP:30,DELTA_A:0.2,DELTA_B:0.3,FAN:0,ROUTE:A",
        "TEMP:36,DELTA_A:0.2,DELTA_B:0.3,FAN:35,ROUTE:A",
        "TEMP:36,DELTA_A:0.7,DELTA_B:0.2,FAN:35,ROUTE:A",
        "TEMP:42,DELTA_A:0.7,DELTA_B:0.2,FAN:100,ROUTE:A"
    ]

    for message in test_messages:
        process_sensor_data(message)
