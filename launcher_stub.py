"""GeoPort launcher stub - a real .exe so Windows will pin it to the taskbar.

Windows refuses to taskbar-pin .bat/.ps1 shortcuts, so this tiny stub exists
to be the pinnable target. It does nothing but launch GeoPort.bat, which
keeps all the real logic (already-running check, one UAC elevation, pythonw
launch, browser open) in one place.

Build (from the repo root, with the .venv or the dev venv):
    python -m PyInstaller --onefile --windowed --name GeoPort --icon GeoPort.ico \
        --distpath launcher-dist --workpath build-py --specpath build-py \
        launcher_stub.py
    (then move launcher-dist\GeoPort.exe to the repo root)

Location of GeoPort.bat:
    1. the GEOPORT_HOME environment variable, if set; else
    2. a "path.txt" next to the exe containing the repo path; else
    3. the compiled-in default below.
"""
import os
import subprocess
import sys

DEFAULT_REPO = r"C:\Users\cconl\dev\geoport"


def find_bat():
    candidates = []
    env_home = os.environ.get("GEOPORT_HOME")
    if env_home:
        candidates.append(os.path.join(env_home, "GeoPort.bat"))
    try:
        exe_dir = os.path.dirname(sys.executable)
        with open(os.path.join(exe_dir, "path.txt"), encoding="utf-8") as f:
            maybe = f.read().strip()
            if maybe:
                candidates.append(os.path.join(maybe, "GeoPort.bat"))
    except OSError:
        pass
    candidates.append(os.path.join(DEFAULT_REPO, "GeoPort.bat"))
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def main():
    bat = find_bat()
    if bat is None:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0,
            "GeoPort.bat not found.\n\nLooked at:\n  - GEOPORT_HOME env var\n"
            "  - path.txt next to this exe\n  - " + DEFAULT_REPO +
            "\n\nCreate a path.txt next to this exe containing the GeoPort "
            "repo path.",
            "GeoPort launcher", 0x10,
        )
        sys.exit(1)
    subprocess.Popen(bat, cwd=os.path.dirname(bat))


if __name__ == "__main__":
    main()
