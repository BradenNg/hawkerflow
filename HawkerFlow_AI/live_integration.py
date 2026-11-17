import serial
import time

# Change COM3 to the actual ESP32's port
PORT = "COM3"
BAUD_RATE = 115200

try:
    esp32 = serial.Serial(
        PORT,
        BAUD_RATE,
        timeout=2
    )

    time.sleep(2)

    print("Connected to ESP32!")
    print("Waiting for sensor data...")

    while True:
        message = esp32.readline().decode(
            "utf-8", errors="replace"
        ).strip()

        if message:
            print("ESP32 says:", message)

except serial.SerialException as e:
    print("Connection error:", e)

except KeyboardInterrupt:
    print("\nConnection stopped.")

finally:
    if "esp32" in locals() and esp32.is_open:
        esp32.close()



