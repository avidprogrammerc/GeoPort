"""Smoke tests for the GeoPort Flask app (no device required).

Run from the repo root:
    .venv\\Scripts\\python -m pytest tests -q
(or any pytest 7+ on PATH)

These exercise the HTTP layer and the non-device state (validation, saved
locations, log tail, health/route status shapes). Device-dependent flows
(connect, set_location, route walking) need a real iOS device.
"""
import importlib.util
import json
import logging
import os
import socket
import sys
import threading
import time
import urllib.request

import pytest


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    """Import src/main.py as a module with its on-disk state in a temp dir.

    - sys.argv is stubbed so the module-level argparse doesn't see pytest's
      arguments.
    - cwd is a temp dir so GeoPort.log lands there.
    - home_dir is a temp dir so saved locations don't touch the real home.
    The __main__ guard keeps app.run() from executing on import.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    main_py = os.path.join(root, "src", "main.py")

    tmp = tmp_path_factory.mktemp("geoport")
    old_cwd, old_argv = os.getcwd(), sys.argv
    os.chdir(str(tmp))
    sys.argv = [sys.argv[0]]
    try:
        spec = importlib.util.spec_from_file_location("geoport_main", main_py)
        m = importlib.util.module_from_spec(spec)
        # Register before exec: Flask resolves its root/template paths from
        # the module in sys.modules, not from the spec.
        sys.modules["geoport_main"] = m
        spec.loader.exec_module(m)
        m.home_dir = str(tmp)  # keep ~/.geoport writes inside the sandbox
        yield m
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)
        sys.modules.pop("geoport_main", None)


@pytest.fixture()
def client(mod):
    return mod.app.test_client()


def test_index_serves_ui(client):
    r = client.get("/")
    assert r.status_code == 200
    body = r.data.decode("utf-8")
    assert 'class="dark-mode"' in body          # dark mode is the default
    assert "tunnelBanner" in body               # watchdog banner
    assert "savedLocations" in body             # presets UI
    assert "activityLogPanel" in body           # live log panel
    assert "serverInfoPanel" in body            # server info panel
    assert "/server_info" in body               # server info fetch
    assert "api.geoport.me" not in body         # telemetry removed
    assert "NordVPN" not in body                # promo banner removed
    assert r.headers.get("Cache-Control") == "no-store"


def test_connection_status_shape(client):
    r = client.get("/connection_status")
    assert r.status_code == 200
    data = r.get_json()
    for key in ("status", "udid", "rsd_data", "last_location"):
        assert key in data
    assert data["status"] in ("disconnected", "connecting", "connected")


def test_health_shape(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.get_json()
    for key in ("connected", "tunnel_ok", "location_active",
                "route_active", "route_paused", "route_error"):
        assert key in data


def test_route_status_shape(client):
    r = client.get("/route_status")
    assert r.status_code == 200
    data = r.get_json()
    assert data["points"] == 0
    assert data["active"] is False
    assert 0.0 <= data["progress"] <= 1.0


def test_route_start_validation(client):
    # fewer than 2 points
    r = client.post("/route_start", json={"points": [[1.0, 2.0]]})
    assert r.status_code == 400
    # invalid point shape
    r = client.post("/route_start", json={"points": [["nope"]]})
    assert r.status_code == 400
    # out-of-range speed
    r = client.post("/route_start",
                    json={"points": [[1.0, 2.0], [3.0, 4.0]], "speed_kmh": 999})
    assert r.status_code == 400
    # no device connected -> 400 even with a valid route
    r = client.post("/route_start",
                    json={"points": [[1.0, 2.0], [3.0, 4.0]], "speed_kmh": 5})
    assert r.status_code == 400
    assert "connect" in r.get_json()["error"].lower()


def test_haversine(mod):
    # Sydney -> Melbourne ~ 713 km (great circle)
    d = mod.haversine_m(-33.8688, 151.2093, -37.8136, 144.9631)
    assert 700_000 < d < 730_000
    assert mod.haversine_m(0, 0, 0, 0) == 0


def test_saved_locations_roundtrip(client):
    r = client.post("/locations", json={"name": "Test", "lat": 1.5, "lng": 2.5})
    assert r.status_code == 200
    items = r.get_json()
    assert {"name": "Test", "lat": 1.5, "lng": 2.5} in items

    # upsert: same name replaces
    r = client.post("/locations", json={"name": "Test", "lat": 3.5, "lng": 4.5})
    names = [i["name"] for i in r.get_json()]
    assert names.count("Test") == 1

    # validation
    assert client.post("/locations", json={"name": "", "lat": 0, "lng": 0}).status_code == 400
    assert client.post("/locations", json={"name": "X", "lat": 999, "lng": 0}).status_code == 400

    # delete
    r = client.delete("/locations/Test")
    assert r.status_code == 200
    assert [i["name"] for i in r.get_json()] == []
    assert client.get("/locations").get_json() == []


def test_log_tail(client):
    r = client.get("/log_tail?lines=5")
    assert r.status_code == 200
    assert r.content_type.startswith("text/plain")
    assert len(r.data.decode("utf-8").strip().splitlines()) <= 5


def test_token_off_by_default(client):
    # Without GEOPORT_TOKEN, mutating endpoints must not 401.
    r = client.post("/route_stop")
    assert r.status_code != 401


def test_api_md_lists_new_endpoints(mod):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    api_md = open(os.path.join(root, "API.md"), encoding="utf-8").read()
    for ep in ("/route_start", "/route_stop", "/route_status", "/health",
               "/server_info", "/locations", "/log_tail", "/connection_status"):
        assert ep in api_md


# --- Server info -------------------------------------------------------------

def test_server_info_shape(client):
    r = client.get("/server_info")
    assert r.status_code == 200
    data = r.get_json()
    for key in ("version", "port", "auth_enabled", "is_admin", "python_version"):
        assert key in data
    assert isinstance(data["port"], int)
    assert isinstance(data["auth_enabled"], bool)
    assert isinstance(data["is_admin"], bool)
    assert isinstance(data["version"], str)
    assert isinstance(data["python_version"], str)


def test_server_info_values(mod, client, monkeypatch):
    monkeypatch.setattr(mod, "chosen_port", 59999)
    monkeypatch.setattr(mod, "GEOPORT_TOKEN", "secret")
    data = client.get("/server_info").get_json()
    assert data["port"] == 59999
    assert data["auth_enabled"] is True
    assert data["version"] == mod.APP_VERSION_NUMBER
    assert data["python_version"] == sys.version


def test_server_info_auth_off_by_default(client):
    # Without GEOPORT_TOKEN in the environment, auth must report disabled.
    data = client.get("/server_info").get_json()
    assert data["auth_enabled"] is False


# --- Port selection (instant-crash-on-launch regression, WSAEACCES 10013) ---

def test_is_port_in_use_detects_ipv4_listener(mod):
    # The check used to connect to 'localhost', which on Windows resolves to
    # ::1 (IPv6) and misses an IPv4-only 127.0.0.1 listener on the port.
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    port = s.getsockname()[1]
    try:
        assert mod.is_port_in_use(port) is True
    finally:
        s.close()
    assert mod.is_port_in_use(port) is False


def test_port_selection_skips_busy_port(mod):
    # Preferred port already LISTENing -> a different, verified port is used.
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    busy = blocker.getsockname()[1]
    old_preferred = mod.flask_port
    mod.flask_port = busy
    try:
        sock, port = mod.try_bind_listener_on_free_port()
    finally:
        mod.flask_port = old_preferred
        blocker.close()
    try:
        assert sock is not None
        assert port != busy
    finally:
        sock.close()


def test_port_selection_survives_bind_failure(mod, monkeypatch):
    # The original crash: a port that looks free fails bind() with
    # WSAEACCES (10013) because Windows re-rolls ephemeral exclusion ranges
    # on every boot. Any OSError from bind must trigger the next candidate,
    # not just EADDRINUSE.
    calls = []
    real = mod._verified_port_socket

    def fake(port):
        calls.append(port)
        if len(calls) == 1:
            mod.logger.warning(
                f'Port {port} not usable (bind failed: '
                'An attempt was made to access a socket in a way forbidden by its access permissions'
                ') - trying next')
            return None
        return real(port)

    monkeypatch.setattr(mod, "_verified_port_socket", fake)
    sock, port = mod.try_bind_listener_on_free_port()
    try:
        assert calls[0] == mod.flask_port  # preferred tried first
        assert port != calls[0]
        assert sock is not None
    finally:
        sock.close()


def test_rejected_port_is_logged(mod, caplog):
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    busy = blocker.getsockname()[1]
    old_preferred = mod.flask_port
    mod.flask_port = busy
    try:
        with caplog.at_level(logging.INFO, logger="GeoPort"):
            sock, port = mod.try_bind_listener_on_free_port()
    finally:
        mod.flask_port = old_preferred
        blocker.close()
        sock.close()
    messages = [r.getMessage() for r in caplog.records]
    assert any(f"Port {busy} in use" in m for m in messages)
    assert any(f"Serving: http://localhost:{port}" in m for m in messages)


@pytest.mark.skipif(sys.platform != "win32", reason="pyuac elevation path is Windows-only")
def test_admin_relaunch_exits_parent(mod, monkeypatch):
    # pyuac.runAsAdmin() blocks until the elevated child exits and then
    # returns; the non-elevated parent used to continue and start a second
    # instance. It must sys.exit() instead (documented pyuac pattern).
    monkeypatch.setattr(mod.pyuac, "isUserAdmin", lambda: False)
    monkeypatch.setattr(mod.pyuac, "runAsAdmin", lambda: 42)
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 42


def test_port_file_written(mod):
    # The launchers (start.ps1 / GeoPort.bat) rely on GeoPort.port to find
    # the UI when the fallback port is in use.
    sock, port = mod.try_bind_listener_on_free_port()
    try:
        with open(os.path.join(os.getcwd(), "GeoPort.port"), encoding="utf-8") as f:
            assert f.read().strip() == str(port)
    finally:
        sock.close()


def test_flask_serves_on_verified_port(mod):
    # End-to-end: the verified socket actually serves HTTP. On a machine
    # where 54321 is in an OS ephemeral exclusion range this is what the old
    # app.run() path crashed on.
    web_socket, port = mod.try_bind_listener_on_free_port()
    server = mod.make_server("127.0.0.1", port, mod.app, fd=web_socket.fileno())
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        body = None
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/connection_status", timeout=1) as r:
                    body = r.read()
                break
            except Exception:
                time.sleep(0.2)
        assert body is not None and b'"status"' in body
    finally:
        server.shutdown()
        server.server_close()
        web_socket.close()
