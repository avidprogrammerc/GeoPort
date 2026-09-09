"""System tray icon for GeoPort.

Best effort: if pystray/Pillow are missing or there is no usable system
tray (tests, headless), the app runs exactly as before without one.
"""
import threading
import time
import webbrowser

try:
    import pystray
    from PIL import Image, ImageDraw
    _HAS_TRAY = True
except ImportError:
    _HAS_TRAY = False


def _make_icon():
    """A small map-pin drawn with Pillow (no .ico asset needed)."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([12, 6, 52, 46], fill=(16, 145, 116, 255))       # pin head
    d.polygon([(22, 42), (42, 42), (32, 60)], fill=(16, 145, 116, 255))  # tail
    d.ellipse([24, 18, 40, 34], fill=(255, 255, 255, 255))     # hole
    return img


def start_tray(get_state, url, on_quit, title="GeoPort"):
    """Start the tray icon in a background thread.

    get_state() -> (tooltip, status_line) is polled every few seconds so
    the menu stays current. on_quit() is invoked after "Quit" is chosen
    (the icon is stopped first). Returns the pystray Icon, or None when
    no tray is available.
    """
    if not _HAS_TRAY:
        return None

    status_item = pystray.Menu.Item("starting…", lambda icon, item: None, enabled=False)

    def _refresh():
        try:
            tooltip, line = get_state()
        except Exception:
            tooltip, line = title, "error reading status"
        status_item.text = line
        try:
            icon.title = tooltip
        except Exception:
            pass

    def _quit(icon, item):
        threading.Thread(target=icon.stop, daemon=True).start()
        try:
            on_quit()
        except Exception:
            pass

    icon = pystray.Icon(
        "geoport",
        _make_icon(),
        title,
        (
            pystray.Menu.Item("Open GeoPort", lambda icon, item: webbrowser.open(url)),
            pystray.Menu.SEPARATOR,
            status_item,
            pystray.Menu.SEPARATOR,
            pystray.Menu.Item("Quit", _quit),
        ),
    )

    def _runner():
        _refresh()
        icon.run_detached()

    def _ticker():
        # Keep the status line / tooltip current while the icon is alive.
        while True:
            time.sleep(5)
            try:
                _refresh()
            except Exception:
                break

    threading.Thread(target=_runner, daemon=True, name="geoport-tray").start()
    threading.Thread(target=_ticker, daemon=True, name="geoport-tray-ticker").start()
    return icon
