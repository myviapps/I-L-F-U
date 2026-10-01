"""The desktop window: record a call, stop, get a transcript. Uses tkinter (ships with Python)."""

from __future__ import annotations

import contextlib
import os
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from . import __version__
from .capture import Recorder, get_backend
from .hardware import choose_tier, detect_hardware
from .paths import data_dir, new_session_dir
from .session import transcribe_session
from .transcript import to_markdown
from .uninstall import launch_uninstaller

CONSENT = (
    "Before you record:\n\n"
    "Tell everyone on the call that you are recording, and make sure that is allowed where "
    "you and they live and by your meeting platform.\n\n"
    "Audio stays on this computer. Start recording?"
)


class App:
    def __init__(self, root: tk.Tk, backend: str = "auto") -> None:
        self.root = root
        self.backend_name = backend
        self.recorder: Recorder | None = None
        self.session_dir: Path | None = None
        self.started_at = 0.0
        self.transcriber = None
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.last_markdown = ""

        root.title(f"I-L-F-U Call Transcriber {__version__}")
        root.geometry("760x560")
        self._build_menu()
        self._build_body()
        root.protocol("WM_DELETE_WINDOW", self.quit)
        self._poll()

    # ---- layout ----
    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Open recordings folder", command=self.open_folder)
        file_menu.add_command(label="Save transcript as...", command=self.save_as)
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self.quit)
        menubar.add_cascade(label="File", menu=file_menu)
        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="About", command=self.about)
        help_menu.add_command(label="Uninstall...", command=self.uninstall)
        menubar.add_cascade(label="Help", menu=help_menu)
        self.root.config(menu=menubar)

    def _build_body(self) -> None:
        tier = choose_tier(detect_hardware())
        top = ttk.Frame(self.root, padding=12)
        top.pack(fill="x")
        self.record_button = ttk.Button(top, text="Start recording", command=self.toggle)
        self.record_button.pack(side="left")
        self.timer = ttk.Label(top, text="00:00")
        self.timer.pack(side="left", padx=12)
        self.status = ttk.Label(top, text="Ready", anchor="w")
        self.status.pack(side="left", fill="x", expand=True)
        info = f"Model for this computer: {tier.model} ({tier.name} tier). All processing is local."
        ttk.Label(self.root, text=info, padding=(12, 0)).pack(fill="x")
        self.text = scrolledtext.ScrolledText(self.root, wrap="word", height=20)
        self.text.pack(fill="both", expand=True, padx=12, pady=12)
        self.text.insert("1.0", "Your transcript will appear here after you stop recording.")
        self.text.config(state="disabled")

    # ---- actions ----
    def toggle(self) -> None:
        if self.recorder is None:
            self.start()
        else:
            self.stop()

    def start(self) -> None:
        if not messagebox.askokcancel("Recording consent", CONSENT, parent=self.root):
            return
        try:
            backend = get_backend(self.backend_name)
            self.session_dir = new_session_dir()
            self.recorder = Recorder(
                {"system": backend.open_system_audio(), "mic": backend.open_microphone()},
                self.session_dir,
            )
            self.recorder.start()
        except Exception as exc:  # noqa: BLE001 - show any device problem in plain words
            self.recorder = None
            messagebox.showerror("Could not start recording", str(exc), parent=self.root)
            return
        self.started_at = time.time()
        self.record_button.config(text="Stop and transcribe")
        self._set_status("Recording... you can switch back to your call")
        self._tick()

    def stop(self) -> None:
        recorder, self.recorder = self.recorder, None
        self.record_button.config(text="Start recording", state="disabled")
        if recorder is None or self.session_dir is None:
            return
        try:
            recorder.stop()
        except Exception as exc:  # noqa: BLE001 - report, never crash the window
            messagebox.showerror("Problem while stopping", str(exc), parent=self.root)
        self._set_status("Transcribing (the first time this downloads the model)...")
        threading.Thread(target=self._transcribe, args=(self.session_dir,), daemon=True).start()

    def _transcribe(self, session_dir: Path) -> None:
        try:
            if self.transcriber is None:
                from .transcribe import FasterWhisperTranscriber

                self.transcriber = FasterWhisperTranscriber(choose_tier(detect_hardware()))
            segments = transcribe_session(session_dir, self.transcriber)
            markdown = to_markdown(segments) if segments else "(No speech found.)\n"
            (session_dir / "transcript.md").write_text(markdown, encoding="utf-8")
            self.events.put(("done", markdown))
        except Exception as exc:  # noqa: BLE001 - any failure is reported in the window
            self.events.put(("error", str(exc)))

    def open_folder(self) -> None:
        folder = self.session_dir.parent if self.session_dir else data_dir()
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(folder)  # type: ignore[attr-defined]
        else:
            messagebox.showinfo("Recordings folder", str(folder), parent=self.root)

    def save_as(self) -> None:
        if not self.last_markdown:
            messagebox.showinfo("Nothing to save", "Record a call first.", parent=self.root)
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".md", filetypes=[("Markdown", "*.md"), ("Text", "*.txt")]
        )
        if path:
            Path(path).write_text(self.last_markdown, encoding="utf-8")

    def about(self) -> None:
        messagebox.showinfo(
            "About",
            f"I-L-F-U Call Transcriber {__version__}\n"
            "Free, open source (AGPL-3.0). Audio never leaves your computer.\n"
            "https://github.com/myviapps/I-L-F-U",
            parent=self.root,
        )

    def uninstall(self) -> None:
        if not messagebox.askyesno(
            "Uninstall",
            "Remove I-L-F-U from this computer?\n\nYou will be asked whether to keep your "
            "recordings and transcripts.",
            parent=self.root,
        ):
            return
        message = launch_uninstaller()
        messagebox.showinfo("Uninstall", message, parent=self.root)
        if message.startswith("The uninstaller has started"):
            self.quit()

    def quit(self) -> None:
        if self.recorder is not None:
            with contextlib.suppress(Exception):
                self.recorder.stop()
            self.recorder = None
        self.root.destroy()

    # ---- background updates ----
    def _set_status(self, text: str) -> None:
        self.status.config(text=text)

    def _show(self, text: str) -> None:
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", text)
        self.text.config(state="disabled")

    def _tick(self) -> None:
        if self.recorder is None:
            return
        seconds = int(time.time() - self.started_at)
        self.timer.config(text=f"{seconds // 60:02d}:{seconds % 60:02d}")
        self.root.after(500, self._tick)

    def _poll(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                self.record_button.config(state="normal")
                if kind == "done":
                    self.last_markdown = str(payload)
                    self._show(self.last_markdown)
                    self._set_status(f"Done. Saved in {self.session_dir}")
                else:
                    self._set_status("Transcription failed")
                    messagebox.showerror("Transcription failed", str(payload), parent=self.root)
        except queue.Empty:
            pass
        self.root.after(200, self._poll)


def main(backend: str = "auto") -> int:
    root = tk.Tk()
    App(root, backend)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
