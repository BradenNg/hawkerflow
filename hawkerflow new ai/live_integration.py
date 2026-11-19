
import csv
import serial

# Change COM3 to your actual ESP32 port
PORT = "COM3"
BAUD_RATE = 115200

COLUMNS = [
    "millis", "temp_c", "humidity",
    "pressure", "pressure2", "pressure_diff",
    "fan_a_pct", "fan_b_pct", "damper_closed",
    "rpm_a", "rpm_b", "state"
]


def process_csv_line(line):
    values = next(csv.reader([line]))

    if not values:
        return

    # Ignore header announcements
    if values[0].strip().upper() == "HEADER":
        print("ESP32 CSV header received")
        return

    # Some ESP32 programs start data rows with DATA
    if values[0].strip().upper() == "DATA":
        values = values[1:]

    if len(values) != len(COLUMNS):
        print("Skipped unexpected row:", line)
        return

    data = dict(zip(COLUMNS, values))

    try:
        temperature = float(data["temp_c"])
        pressure_1 = float(data["pressure"])
        pressure_2 = float(data["pressure2"])
        pressure_difference = float(
            data["pressure_diff"]
        )

        print("\n--------------------------")
        print("Temperature:", temperature, "C")
        print("Pressure 1:", pressure_1)
        print("Pressure 2:", pressure_2)
        print("Pressure difference:", pressure_difference)
        print("Fan A:", data["fan_a_pct"], "%")
        print("Fan B:", data["fan_b_pct"], "%")
        print("Damper closed:", data["damper_closed"])
        print("State:", data["state"])

        # Blockage logic will be connected
        # after confirming sensor mapping.

    except ValueError:
        print("Invalid sensor values:", line)


try:
    with serial.Serial(
        PORT, BAUD_RATE, timeout=2
    ) as esp32:

        print("Connected to ESP32!")
        print("Reading CSV sensor data...")

        while True:
            line = esp32.readline().decode(
                "utf-8", errors="replace"
            ).strip()

            if line:
                process_csv_line(line)

except serial.SerialException as error:
    print("Serial connection error:", error)

except KeyboardInterrupt:
    print("\nStopped.")
