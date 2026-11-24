"""HawkerFlow simulation dashboard - no ESP32 needed.

A pretend ESP32 that talks exactly like HawkerFlow.ino, connected to the same
AI / vent logic as live_integration.py, with a control panel on the web page:
  - temperature: automatic cooking cycle, or set it yourself with a slider
  - clog / clean filter A or B
  - switch the ESP32 off / on, press RST, or make it stop sending data

Run:   python simulation.py          -> http://localhost:8001
It uses a different port from dashboard.py (8000), so both can run at once.
"""
import argparse
import collections
import random
import threading
import time

import dashboard
from dashboard import li


class SimulatedESP32:
    """Behaves like HawkerFlow.ino on the serial port, without any hardware."""
    PERIOD = 2.0                        # one DATA line every 2 s, like the firmware
    CYCLE = 180                         # automatic temperature cycle length (s)

    def __init__(self):
        self.lock = threading.Lock()
        self.powered = True
        self.muted = False              # on, but not sending DATA lines
        self.temp_mode = "auto"
        self.manual_temp = 36.0
        self.clogged = {"A": False, "B": False}
        self.boot()

    # ----- what the firmware does on every start-up -----
    def boot(self):
        self.start = time.time()
        self.next_at = self.start + 1
        self.fan = 100                  # OFFLINE start-up speed
        self.mask = 0                   # both vents open
        self.state = "OFFLINE"
        self.replies = collections.deque(["INFO,pressure sensor 1 connected - zeroed",
                                          "INFO,pressure sensor 2 connected - zeroed",
                                          "INFO,pressure sensor 3 connected - zeroed"])

    # ----- serial port interface used by dashboard.serial_loop -----
    def open(self):
        if not self.powered:
            raise OSError("The simulated ESP32 is switched OFF - press 'Power on' in the control panel.")
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def reset_input_buffer(self):
        pass

    def write(self, raw):
        line = raw.decode().strip()
        with self.lock:
            if not self.powered:
                return
            if line.startswith("SPEED "):
                self.fan = int(line.split()[1])
                self.replies.append(f"ACK,SPEED,{self.fan}")
            elif line.startswith("VENT "):
                _, v, action = line.split()
                bit = 1 if v == "A" else 2
                self.mask = self.mask | bit if action == "CLOSE" else self.mask & ~bit
                self.replies.append(f"ACK,VENT,{v},{'CLOSED' if self.mask & bit else 'OPEN'}")
            elif line.startswith("PREDICTION:"):
                self.state = line.split(":", 1)[1]
                self.replies.append(f"ACK,PREDICTION,{self.state},2/2")

    def readline(self):
        with self.lock:
            if not self.powered:
                raise OSError("The simulated ESP32 was switched off (USB unplugged).")
            if self.replies:
                return (self.replies.popleft() + "\n").encode()
            wait = self.next_at - time.time()
            if wait <= 0:
                self.next_at += self.PERIOD
                if not self.muted:
                    return (self.data_line() + "\n").encode()
                wait = self.PERIOD
        time.sleep(min(wait, 0.25))     # short naps keep the buttons responsive
        return b""

    # ----- the physics (numbers based on real_pressure_data.csv) -----
    def temperature(self):
        if self.temp_mode == "manual":
            return self.manual_temp + random.uniform(-0.2, 0.2)
        phase = (time.time() - self.start) % self.CYCLE
        if phase < 30:
            base = 29                                   # idle
        elif phase < 50:
            base = 29 + (phase - 30) * 0.35             # warming up
        elif phase < 90:
            base = 36                                   # cooking  -> fan 35%
        elif phase < 150:
            base = 42                                   # wok hei  -> fan 100%
        else:
            base = 42 - (phase - 150) * 0.4             # cooling down
        return base + random.uniform(-0.3, 0.3)

    def drop(self, v, bit):
        if self.fan == 0:
            return random.uniform(-0.1, 0.1)
        if self.mask & bit:                             # closed: almost no air through it
            return random.uniform(-0.05, 0.1)
        if self.clogged[v]:
            return 8 * self.fan / 100 + random.uniform(-0.4, 0.4)
        return 0.15 + random.uniform(-0.1, 0.1)

    def data_line(self):
        t = time.time() - self.start
        temp = self.temperature()
        pa = -0.1 * self.fan / 35 + random.uniform(-0.05, 0.05)
        da, db = self.drop("A", 1), self.drop("B", 2)
        pc, pb = pa + da, pa + db
        rpm = self.fan * 32 + random.uniform(-40, 40) if self.fan else 0
        return (f"DATA,{int(t * 1000)},{temp:.1f},{60 + random.uniform(-3, 3):.1f},"
                f"{pa:.1f},{pb:.1f},{pc:.1f},{pb - pa:.1f},{pc - pa:.1f},"
                f"{self.fan},{self.fan},{self.mask},{rpm:.0f},{rpm:.0f},{self.state}")

    # ----- control panel (called from the web page) -----
    def control(self, action, value):
        with self.lock:
            if action == "power":
                on = value == "on"
                if on == self.powered:
                    return None
                self.powered = on
                if on:
                    self.boot()
                return f"Simulated ESP32 switched {'ON' if on else 'OFF'}"
            if action == "rst":
                if not self.powered:
                    return None
                self.boot()
                return "Simulated ESP32: RST pressed (restarting)"
            if action == "mute":
                self.muted = value == "on"
                return "Simulated ESP32 " + ("stopped sending data" if self.muted else "is sending data again")
            if action == "clog" and value.upper() in self.clogged:
                v = value.upper()
                self.clogged[v] = not self.clogged[v]
                return f"Simulated filter {v} is now {'CLOGGED' if self.clogged[v] else 'clean'}"
            if action == "temp":
                if value == "auto":
                    self.temp_mode = "auto"
                    return "Temperature: automatic cooking cycle"
                try:
                    t = max(20.0, min(50.0, float(value)))
                except ValueError:
                    return None
                was_manual = self.temp_mode == "manual"
                self.temp_mode, self.manual_temp = "manual", t
                return None if was_manual else "Temperature: set by hand"
        return None

    def status(self):
        phase = (time.time() - self.start) % self.CYCLE
        if self.temp_mode == "manual":
            step = "manual"
        elif phase < 30:
            step = "idle"
        elif phase < 50:
            step = "warming up"
        elif phase < 90:
            step = "cooking"
        elif phase < 150:
            step = "wok hei (hot)"
        else:
            step = "cooling down"
        return {
            "powered": self.powered, "muted": self.muted,
            "temp_mode": self.temp_mode, "manual_temp": self.manual_temp,
            "cycle_step": step, "cycle_left": None if self.temp_mode == "manual" else int(self.CYCLE - phase),
            "clogged": dict(self.clogged),
        }


def main():
    parser = argparse.ArgumentParser(description="HawkerFlow simulation dashboard (no ESP32 needed)")
    parser.add_argument("--web-port", type=int, default=8001, help="page port (default 8001)")
    parser.add_argument("--no-browser", action="store_true", help="don't open the browser")
    args = parser.parse_args()

    esp = SimulatedESP32()
    dashboard.sim = esp
    dashboard.serve("sim", "Simulated ESP32", esp.open, args.web_port, not args.no_browser)


if __name__ == "__main__":
    main()
