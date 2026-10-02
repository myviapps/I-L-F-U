"""Opens the app: starts the local server and shows it in its own window.

The window is the Edge or Chrome that is already on the computer, started in "app mode" (no tabs,
no address bar), so the program looks and feels like a normal desktop app.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import urllib.request
import webbrowser
from pathlib import Path

from . import __version__
from .config import config_path
from .core import Controller
from .server import COOKIE, IlfuServer

log = logging.getLogger("ilfu")


def _state_dir() -> Path:
    return config_path().parent


def _setup_log() -> None:
    """pythonw shows no console, so errors go to a file the user can send us."""
    path = _state_dir() / "ilfu.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=path, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    log.info("I-L-F-U %s starting on %s", __version__, sys.platform)


def _browser_candidates() -> list[str]:
    found: list[str] = []
    if sys.platform == "win32":
        for var in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
            base = os.environ.get(var)
            if base:
                found += [
                    str(Path(base) / "Microsoft/Edge/Application/msedge.exe"),
                    str(Path(base) / "Google/Chrome/Application/chrome.exe"),
                ]
    else:
        for name in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge"):
            path = shutil.which(name)
            if path:
                found.append(path)
        if sys.platform == "darwin":
            found.append("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    return [p for p in found if Path(p).exists()]


def open_window(url: str) -> None:
    """Show the app in its own window; fall back to the default browser."""
    profile = _state_dir() / "window-profile"
    for exe in _browser_candidates():
        try:
            subprocess.Popen(
                [exe, f"--app={url}", f"--user-data-dir={profile}", "--window-size=1200,800",
                 "--no-first-run", "--no-default-browser-check"]
            )
            return
        except OSError:
            log.exception("could not start %s", exe)
    webbrowser.open(url)


def _instance_file() -> Path:
    return _state_dir() / "server.json"


def _running_instance() -> str | None:
    """The address of an app that is already running, so a second launch reuses it."""
    try:
        info = json.loads(_instance_file().read_text(encoding="utf-8"))
        req = urllib.request.Request(
            f"http://127.0.0.1:{info['port']}/api/state", headers={"Cookie": f"{COOKIE}={info['token']}"}
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            if resp.status == 200:
                return f"http://127.0.0.1:{info['port']}/?t={info['token']}"
    except (OSError, ValueError, KeyError):
        pass
    return None


def main(backend: str = "auto", show_window: bool = True) -> int:
    with contextlib.suppress(OSError):
        _setup_log()
    existing = _running_instance()
    if existing:
        if show_window:
            open_window(existing)
        return 0
    controller = Controller(backend)
    server = IlfuServer(controller)
    state_file = _instance_file()
    with contextlib.suppress(OSError):
        state_file.write_text(
            json.dumps({"port": server.server_address[1], "token": server.token}), encoding="utf-8"
        )
    threading.Thread(target=server.watchdog, daemon=True, name="ilfu-watchdog").start()
    if show_window:
        open_window(server.url)
    else:
        print(server.url)
    try:
        server.serve_forever()
    finally:
        controller.shutdown()
        server.server_close()
        with contextlib.suppress(OSError):
            state_file.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(show_window="--no-window" not in sys.argv))
