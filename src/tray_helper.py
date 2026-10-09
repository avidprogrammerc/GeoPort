"""GeoPort menu bar helper (macOS).

The main app must run elevated on macOS (see the os.geteuid() check in
main.py), but AppKit cannot display a status item from a root process.
This helper runs as the regular user: it shows the pystray menu-bar icon
and polls the app's localhost HTTP API for live status.

- "Open GeoPort" opens the web UI in the browser.
- "Quit" posts to the app's /exit endpoint (clean shutdown_server).
- If the app never appears (e.g. the password dialog was cancelled) or
  disappears later, the helper exits on its own.
"""
import json
import os
import re
import sys
import time
import threading
import urllib.request
import webbrowser

LOG_PATH = os.path.expanduser("~/Library/Logs/GeoPort/GeoPort.log")
POLL_S = 5
START_TIMEOUT_S = 150  # room for the password dialog
LOST_AFTER = 3  # consecutive failed polls before giving up


def _http(port, path, method="GET", timeout=4):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode()
    try:
        return json.loads(body)
    except (ValueError, TypeError):
        return body


def find_port(timeout=START_TIMEOUT_S):
    """Latest 'Serving:' port from the log that actually responds."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with open(LOG_PATH, errors="replace") as f:
                text = f.read()
        except OSError:
            time.sleep(1)
            continue
        for raw in reversed(re.findall(r"Serving: http://localhost:(\d+)", text)):
            try:
                _http(int(raw), "/health")
                return int(raw)
            except Exception:
                pass
        time.sleep(1)
    return None


def poll_state(port):
    """(status_line, device_line) from the app's HTTP API."""
    line, device = "No device connected", ""
    try:
        rs = _http(port, "/route_status")
        if isinstance(rs, dict):
            if rs.get("paused"):
                line = "Route paused (location held)"
            elif rs.get("active"):
                pts = rs.get("points") or 0
                idx = max(int(rs.get("index") or 0), 0)
                line = f"Walking route: point {idx + 1}/{pts}" if pts else "Walking route"
    except Exception:
        pass
    try:
        devs = _http(port, "/list_devices")
        if isinstance(devs, dict) and devs:
            line = "Device connected"
            names = set()
            for conns in devs.values():
                if not isinstance(conns, dict):
                    continue
                for infos in conns.values():
                    if not isinstance(infos, list):
                        continue
                    for info in infos:
                        if isinstance(info, dict) and info.get("DeviceName"):
                            names.add(info["DeviceName"])
            if names:
                device = f"Device: {sorted(names)[0]}"
    except Exception:
        pass
    return line, device


def _make_icon():
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([12, 6, 52, 46], fill=(16, 145, 116, 255))
    d.polygon([(22, 42), (42, 42), (32, 60)], fill=(16, 145, 116, 255))
    d.ellipse([24, 18, 40, 34], fill=(255, 255, 255, 255))
    return img


def main():
    port = find_port()
    if port is None:
        print("GeoPort helper: app did not start in time; exiting", file=sys.stderr)
        return 1
    url = f"http://localhost:{port}"

    try:
        import pystray
    except ImportError:
        print("GeoPort helper: pystray unavailable; exiting", file=sys.stderr)
        return 1

    status = {"line": "starting…", "device": "", "lost": 0}

    def _open_ui(icon, item=None):
        webbrowser.open(url)

    def _quit(icon, item):
        # /exit triggers shutdown_server in the app; the response may not
        # arrive because the process exits - that is fine.
        try:
            _http(port, "/exit", method="POST")
        except Exception:
            pass
        threading.Thread(target=icon.stop, daemon=True).start()

    def _build_menu():
        items = [
            pystray.MenuItem("Open GeoPort", _open_ui, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(status["line"], lambda icon, item: None, enabled=False),
        ]
        if status["device"]:
            items.append(
                pystray.MenuItem(status["device"], lambda icon, item: None, enabled=False))
        items.append(pystray.Menu.SEPARATOR)
        items.append(pystray.MenuItem("Quit", _quit))
        return pystray.Menu(*items)

    icon = pystray.Icon("geoport", _make_icon(), "GeoPort", _build_menu())

    def _ticker():
        while True:
            time.sleep(POLL_S)
            try:
                line, device = poll_state(port)
                status["line"], status["device"] = line, device
                status["lost"] = 0
            except Exception:
                status["lost"] += 1
            if status["lost"] >= LOST_AFTER:
                # App is gone - stop the icon, main thread exits the loop.
                threading.Thread(target=icon.stop, daemon=True).start()
                return
            try:
                icon.menu = _build_menu()
            except Exception:
                pass

    threading.Thread(target=_ticker, daemon=True, name="geoport-tray-helper").start()
    icon.run()  # blocking; returns once the icon is stopped
    return 0


if __name__ == "__main__":
    sys.exit(main())
