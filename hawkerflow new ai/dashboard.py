"""HawkerFlow web dashboard.

Runs the same AI / vent logic as live_integration.py (it imports it, nothing is
copied or changed) and shows everything live in your browser:
temperature, fan, the pressure drop of each filter, vent open/closed, alerts.

Run (close the Arduino Serial Monitor and live_integration.py first):
    python dashboard.py                 real ESP32 on COM7
    python dashboard.py --com COM5      real ESP32 on another port

Then open  http://localhost:8000  (it opens by itself).
No board? Use  python simulation.py  instead (a separate simulated dashboard).
"""
import argparse
import collections
import io
import json
import math
import os
import queue
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
sim = None                          # set by simulation.py: the simulated ESP32


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


def serial_loop(make_port):
    while True:
        try:
            with make_port() as esp32:
                time.sleep(0 if sim else 2)
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
            if not sim:
                print("Serial:", error, "- retrying in 3 s")
            time.sleep(1 if sim else 3)


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
            "sim": sim.status() if sim else None,
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
        parts = self.path.strip("/").split("/")        # api/vent/A/open, api/sim/<action>/<value>
        if len(parts) == 4 and parts[:2] == ["api", "vent"] and parts[3] == "open":
            commands.put(("open", parts[2].upper()))
        elif len(parts) == 4 and parts[:2] == ["api", "sim"] and sim is not None:
            message = sim.control(parts[2], parts[3])  # works even while the fake ESP32 is "off"
            if message:
                add_event("sim", message)
        else:
            return self.send(404, b"not found", "text/plain")
        self.send(200, b'{"ok":true}', "application/json")

    def log_message(self, *args):                       # keep the console readable
        pass


def serve(mode, port_label, make_port, web_port, open_browser=True):
    """Start the serial thread and the web page. Also used by simulation.py."""
    status["mode"], status["port"] = mode, port_label
    threading.Thread(target=serial_loop, args=(make_port,), daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", web_port), Handler)
    url = f"http://localhost:{web_port}"
    print(f"\nHawkerFlow {'simulation' if mode == 'sim' else 'dashboard'}: {url}   (Ctrl+C to stop)\n")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


def main():
    parser = argparse.ArgumentParser(description="HawkerFlow live dashboard (real ESP32)")
    parser.add_argument("--com", default=li.PORT, help=f"ESP32 serial port (default {li.PORT})")
    parser.add_argument("--web-port", type=int, default=8000, help="dashboard port (default 8000)")
    parser.add_argument("--no-browser", action="store_true", help="don't open the browser")
    parser.add_argument("--demo", action="store_true", help=argparse.SUPPRESS)   # old flag
    args = parser.parse_args()
    if args.demo:
        sys.exit("The simulation is now separate:  python simulation.py   (http://localhost:8001)")

    import serial
    serve("live", args.com, lambda: serial.Serial(args.com, li.BAUD_RATE, timeout=2),
          args.web_port, not args.no_browser)


if __name__ == "__main__":
    main()
