"""HawkerFlow web dashboard.

Runs the same AI / vent logic as live_integration.py (it imports it, nothing is
copied or changed) and shows everything live in your browser:
temperature, fan, the pressure drop of each filter, vent open/closed, alerts.

Run (close the Arduino Serial Monitor and live_integration.py first):
    python dashboard.py                 real ESP32 on COM7
    python dashboard.py --com COM5      real ESP32 on another port
    python dashboard.py --demo          no board needed: a simulated ESP32

Then open  http://localhost:8000  (it opens by itself).
"""
import argparse
import collections
import io
import json
import math
import os
import queue
import random
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)                      # live_integration loads its model from this folder

import live_integration as li      # noqa: E402  (the team's AI + vent logic)

HISTORY_POINTS = 450                # ~15 min of DATA lines at one every 2 s
EVENT_LIMIT = 80

lock = threading.Lock()
commands = queue.Queue()            # web button presses -> serial thread
status = {
    "mode": None, "port": None, "connected": False, "error": None,
    "last_data_at": None, "latest": None, "state": None, "report": {},
    "esp_state": None,
}
history = collections.deque(maxlen=HISTORY_POINTS)
events = collections.deque(maxlen=EVENT_LIMIT)
demo = None                         # FakeESP32 when running with --demo


def add_event(level, text):
    with lock:
        events.append({"t": time.time(), "level": level, "text": text.strip()})


# Warnings from live_integration also go to the web page
_original_warn = li.warn


def _warn(text):
    _original_warn(text)
    add_event("warn", " ".join(line.strip() for line in text.splitlines()))


li.warn = _warn


class Tee(io.TextIOBase):
    """Prints to the console as usual and keeps a copy of this cycle's text."""

    def __init__(self, real):
        self.real, self.buf = real, []

    def write(self, s):
        self.real.write(s)
        self.buf.append(s)
        return len(s)

    def flush(self):
        self.real.flush()


def clean(x):
    """NaN / inf are not valid JSON."""
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return x


def run_cycle(data, esp32):
    """One DATA line: run the team's process() and keep what it decided."""
    real = sys.stdout
    tee = Tee(real)
    sys.stdout = tee
    try:
        li.process(data, esp32)
    finally:
        sys.stdout = real
    text = "".join(tee.buf)

    report, state = {}, None
    for line in text.splitlines():
        s = line.strip()
        for v in li.VENTS:
            if s.startswith(f"Vent {v}:"):
                report[v] = s.split(":", 1)[1].strip()
        if s.startswith("State:"):
            state = s.split(":", 1)[1].strip()
        if s.startswith(">>>") or s.startswith("ESP32 restarted"):
            add_event("info", s.lstrip("> "))

    now = time.time()
    with lock:
        status["latest"] = {k: clean(v) for k, v in data.items()}
        status["last_data_at"] = now
        status["state"] = state
        status["esp_state"] = data.get("state")
        status["report"] = report
        history.append({
            "t": now,
            "temp": clean(data["temp_c"]), "hum": clean(data["humidity"]),
            "dA": clean(data[li.VENT_DELTA["A"]]), "dB": clean(data[li.VENT_DELTA["B"]]),
            "fan": clean(data["fan_b_pct"]), "target": li.last_fan,
            "closedA": bool(li.closed["A"]), "closedB": bool(li.closed["B"]),
        })


def handle_command(cmd, esp32):
    kind, v = cmd
    if kind == "open" and v in li.VENTS:
        with lock:
            li.open_vent(v, esp32)
        add_event("info", f"Vent {v} opened by hand (dashboard)")
    elif kind == "clog" and demo is not None and v in li.VENTS:
        demo.clogged[v] = not demo.clogged[v]
        add_event("demo", f"Simulated filter {v} is now {'CLOGGED' if demo.clogged[v] else 'clean'}")


def serial_loop(make_port):
    while True:
        try:
            with make_port() as esp32:
                time.sleep(0 if demo else 2)
                esp32.reset_input_buffer()
                for v in li.VENTS:            # same start-up as live_integration.main()
                    esp32.write(f"VENT {v} OPEN\n".encode())
                with lock:
                    status["connected"], status["error"] = True, None
                add_event("info", f"Port {status['port']} opened - waiting for the ESP32")
                silent_since, warned = time.time(), False
                while True:
                    while not commands.empty():
                        handle_command(commands.get(), esp32)
                    line = esp32.readline().decode("utf-8", errors="replace").strip()
                    if not line:
                        if not warned and time.time() - silent_since > 10:
                            warned = True
                            add_event("warn", "No data from the ESP32 for 10 s - is it powered on?")
                        continue
                    if warned:
                        add_event("info", "ESP32 is sending again")
                    silent_since, warned = time.time(), False
                    data = li.parse(line)
                    if data is not None:
                        run_cycle(data, esp32)
                    elif line.startswith(("ERR", "INFO")):
                        add_event("esp", line)
        except Exception as error:            # unplugged, wrong port, port busy ...
            text = str(error)
            if "FileNotFound" in text or "could not open port" in text and "Access" not in text:
                text = f"Can't find the ESP32 on {status['port']} (not plugged in, powered off, or a different COM port)."
            elif "Access is denied" in text or "PermissionError" in text:
                text = f"{status['port']} is busy - another program (Serial Monitor / live_integration.py) is using it."
            with lock:
                was = status["connected"]
                status["connected"], status["error"] = False, text
            if was:
                add_event("warn", f"Lost the ESP32: {error}")
            print("Serial:", error, "- retrying in 3 s")
            time.sleep(3)


# ---------------- Simulated ESP32 (--demo) ----------------
class FakeESP32:
    """Behaves like HawkerFlow.ino on the serial port, without any hardware.

    Temperature cycles through not cooking -> cooking -> hot -> cooling every
    3 minutes. Use the 'Simulate clog' buttons on the page to block a filter.
    """
    PERIOD = 2.0

    def __init__(self):
        self.start = time.time()
        self.next_at = self.start + 1
        self.fan = 100                  # OFFLINE start-up speed, like the firmware
        self.mask = 0
        self.clogged = {"A": False, "B": False}
        self.replies = collections.deque()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def reset_input_buffer(self):
        self.replies.clear()

    def write(self, raw):
        line = raw.decode().strip()
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

    def temperature(self, t):
        phase = t % 180
        if phase < 30:
            base = 29
        elif phase < 50:
            base = 29 + (phase - 30) * 0.35     # warming up
        elif phase < 90:
            base = 36                            # cooking
        elif phase < 150:
            base = 42                            # wok hei
        else:
            base = 42 - (phase - 150) * 0.4      # cooling down
        return base + random.uniform(-0.3, 0.3)

    def drop(self, v, bit):
        if self.fan == 0:
            return random.uniform(-0.1, 0.1)
        if self.mask & bit:                      # closed: almost no air through it
            return random.uniform(-0.05, 0.1)
        if self.clogged[v]:                      # like the blocked runs in real_pressure_data.csv
            return 8 * self.fan / 100 + random.uniform(-0.4, 0.4)
        return 0.15 + random.uniform(-0.1, 0.1)

    def readline(self):
        if self.replies:
            return (self.replies.popleft() + "\n").encode()
        wait = self.next_at - time.time()
        if wait > 0:
            time.sleep(min(wait, 0.25))          # stay responsive to button presses
            return b""
        self.next_at += self.PERIOD
        t = time.time() - self.start
        temp = self.temperature(t)
        pa = -0.1 * self.fan / 35 + random.uniform(-0.05, 0.05)
        da, db = self.drop("A", 1), self.drop("B", 2)
        pc, pb = pa + da, pa + db
        rpm = self.fan * 32 + random.uniform(-40, 40) if self.fan else 0
        state = getattr(self, "state", "OFFLINE")
        line = (f"DATA,{int(t * 1000)},{temp:.1f},{60 + random.uniform(-3, 3):.1f},"
                f"{pa:.1f},{pb:.1f},{pc:.1f},{pb - pa:.1f},{pc - pa:.1f},"
                f"{self.fan},{self.fan},{self.mask},{rpm:.0f},{rpm:.0f},{state}")
        return (line + "\n").encode()


# ---------------- Web server ----------------
PAGE = os.path.join(HERE, "dashboard.html")


def snapshot():
    with lock:
        age = time.time() - status["last_data_at"] if status["last_data_at"] else None
        vents = {}
        for v in li.VENTS:
            delta = status["latest"][li.VENT_DELTA[v]] if status["latest"] else None
            vents[v] = {
                "closed": bool(li.closed[v]), "clogged": bool(li.clogged[v]),
                "over_streak": li.over_streak[v], "under_streak": li.under_streak[v],
                "closed_for": time.time() - li.closed_at[v] if li.closed[v] else None,
                "delta": delta, "report": status["report"].get(v, ""),
            }
        return {
            **{k: status[k] for k in ("mode", "port", "connected", "error", "latest", "state", "esp_state")},
            "data_age": age,
            "fan_target": li.last_fan,
            "vents": vents,
            "model": li.MODEL_FILE if li.model is not None else None,
            "limit": li.PRESSURE_LIMIT,
            "settings": {"confirm": li.CONFIRM_READS, "reopen": li.REOPEN_READS, "min_closed": li.MIN_CLOSED_S},
            "demo_clogged": dict(demo.clogged) if demo else None,
            "history": list(history),
            "events": list(events)[::-1],
        }


class Handler(BaseHTTPRequestHandler):
    def send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            with open(PAGE, "rb") as f:
                self.send(200, f.read(), "text/html; charset=utf-8")
        elif self.path == "/api/state":
            self.send(200, json.dumps(snapshot()).encode(), "application/json")
        else:
            self.send(404, b"not found", "text/plain")

    def do_POST(self):
        parts = self.path.strip("/").split("/")        # api/vent/A/open, api/demo/clog/A
        if len(parts) == 4 and parts[:2] == ["api", "vent"] and parts[3] == "open":
            commands.put(("open", parts[2].upper()))
        elif len(parts) == 4 and parts[:3] == ["api", "demo", "clog"]:
            commands.put(("clog", parts[3].upper()))
        else:
            return self.send(404, b"not found", "text/plain")
        self.send(200, b'{"ok":true}', "application/json")

    def log_message(self, *args):                       # keep the console readable
        pass


def main():
    parser = argparse.ArgumentParser(description="HawkerFlow web dashboard")
    parser.add_argument("--com", default=li.PORT, help=f"ESP32 serial port (default {li.PORT})")
    parser.add_argument("--demo", action="store_true", help="use a simulated ESP32")
    parser.add_argument("--web-port", type=int, default=8000, help="dashboard port (default 8000)")
    parser.add_argument("--no-browser", action="store_true", help="don't open the browser")
    args = parser.parse_args()

    global demo
    if args.demo:
        demo = FakeESP32()
        status["mode"], status["port"] = "demo", "simulated ESP32"
        make_port = lambda: demo                        # noqa: E731
    else:
        import serial
        status["mode"], status["port"] = "live", args.com
        make_port = lambda: serial.Serial(args.com, li.BAUD_RATE, timeout=2)  # noqa: E731

    threading.Thread(target=serial_loop, args=(make_port,), daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", args.web_port), Handler)
    url = f"http://localhost:{args.web_port}"
    print(f"\nHawkerFlow dashboard: {url}   (Ctrl+C to stop)\n")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
