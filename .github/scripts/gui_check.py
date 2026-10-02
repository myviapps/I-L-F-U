"""CI only: drive the real window end to end with the fake audio backend and the real model."""

import sys
import time
import tkinter as tk
from tkinter import messagebox

from ilfu import config, library
from ilfu.gui import App

errors: list[str] = []
messagebox.askokcancel = lambda *a, **k: True
messagebox.showerror = lambda *a, **k: errors.append(str(a))
messagebox.showinfo = lambda *a, **k: None

root = tk.Tk()
cfg = config.load()
assert not config.needs_setup(cfg), "setup was not saved"


def pump(seconds: float, until=lambda: False) -> None:
    end = time.time() + seconds
    while time.time() < end and not until():
        root.update()
        time.sleep(0.05)


app = App(root, "fake", cfg)
pump(240, lambda: app.transcriber is not None)
assert app.transcriber is not None, f"speech model did not load: {errors}"
print("model loaded")

app.start()
assert app.recorder is not None, f"could not start: {errors}"
pump(6)
app.toggle_pause()
pump(1)
app.toggle_pause()
pump(3)
app.stop()
pump(120, lambda: not app.busy)
assert not app.busy, "stop never finished"

sessions = library.list_sessions(cfg.sessions_dir())
assert len(sessions) == 1, sessions
folder = sessions[0].path
assert (folder / "mic.wav").exists() and (folder / "system.wav").exists()
assert (folder / "meta.json").exists()
print("recording saved:", folder, f"{sessions[0].duration:.1f}s")
assert not errors, errors
root.destroy()
print("window flow ok")
sys.exit(0)
