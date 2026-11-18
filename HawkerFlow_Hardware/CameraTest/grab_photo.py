"""
Grab a photo from the ESP32-S3 CAM over USB serial and save it as a JPEG.

Setup (once):   pip install pyserial
Usage:          python grab_photo.py COM7
                python grab_photo.py COM7 5      <- take 5 photos

Close the Arduino Serial Monitor first - only one program can use the COM port.
"""
import os
import sys
import time

import serial

port = sys.argv[1] if len(sys.argv) > 1 else "COM7"
count = int(sys.argv[2]) if len(sys.argv) > 2 else 1

ser = serial.Serial(port, 921600, timeout=5)
time.sleep(2)               # board may reset when the port opens
ser.reset_input_buffer()

for n in range(count):
    ser.write(b"c")
    length = None
    deadline = time.time() + 10
    while time.time() < deadline:
        line = ser.readline().decode(errors="ignore").strip()
        if line.startswith("JPG_START"):
            length = int(line.split()[1])
            break
        if line:
            print("board:", line)
    if length is None:
        print("No photo received - is the sketch running and the Serial Monitor closed?")
        sys.exit(1)

    data = ser.read(length)
    if len(data) != length or not data.startswith(b"\xff\xd8"):
        print(f"Bad/partial image ({len(data)}/{length} bytes). Try again.")
        continue

    # always save in a "photos" folder next to this script
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "photos")
    os.makedirs(out_dir, exist_ok=True)
    name = os.path.join(out_dir, time.strftime(f"photo_%Y%m%d_%H%M%S_{n}.jpg"))
    with open(name, "wb") as f:
        f.write(data)
    print(f"Saved {name} ({length} bytes) -> {os.path.abspath(name)}")

ser.close()
