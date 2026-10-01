"""Where the app keeps its files. Everything lives under the user's own folders."""

from __future__ import annotations

import ctypes
import json
import sys
import time
from pathlib import Path

INSTALL_MARKER = "ilfu-install.json"


def install_home() -> Path | None:
    """The folder the Windows install script created, or None if not installed that way.

    The script puts a virtual environment in `<home>/venv` and writes a marker file in `<home>`.
    """
    home = Path(sys.prefix).parent
    return home if (home / INSTALL_MARKER).exists() else None


def model_dir() -> Path | None:
    """Downloaded models go inside the install folder so uninstalling removes them too."""
    home = install_home()
    return home / "models" if home else None


def documents_dir() -> Path:
    if sys.platform == "win32":
        buf = ctypes.create_unicode_buffer(260)
        # 5 = CSIDL_PERSONAL (the user's real Documents folder, even when OneDrive moves it)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0:  # type: ignore[attr-defined]
            return Path(buf.value)
    return Path.home() / "Documents"


def data_dir() -> Path:
    """Recordings and transcripts. Kept when the app is uninstalled unless the user says otherwise."""
    return documents_dir() / "ILFU" / "sessions"


def new_session_dir(base: Path | None = None) -> Path:
    base = base or data_dir()
    path = base / time.strftime("%Y%m%d-%H%M%S")
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_install_info() -> dict:
    home = install_home()
    return json.loads((home / INSTALL_MARKER).read_text(encoding="utf-8")) if home else {}
