"""Start the uninstaller. Used by the CLI (`ilfu uninstall`) and the window's Help menu."""

from __future__ import annotations

import subprocess
import sys

from .paths import install_home


def launch_uninstaller() -> str:
    """Start the Windows uninstall script in its own window. Returns a message for the user."""
    home = install_home()
    if sys.platform != "win32" or home is None:
        return (
            "This copy was not set up by the Windows installer. "
            "If you installed it with pip, remove it with: pip uninstall ilfu"
        )
    script = home / "uninstall.ps1"
    if not script.exists():
        return f"Uninstall script not found: {script}"
    subprocess.Popen(
        [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(script), "-InstallDir", str(home),
        ],
        creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
    )
    return "The uninstaller has started in a new window. Close this program now."
