"""The desktop window. Uses tkinter (ships with Python)."""

from __future__ import annotations

import contextlib
import logging
import os
import queue
import re
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import __version__, library, models, playback, ui
from .capture import Recorder, get_backend
from .config import LANGUAGES, Config, load, needs_setup, save
from .hardware import choose_tier, detect_hardware
from .live import LiveTranscriber
from .paths import new_session_dir
from .session import transcribe_session
from .transcript import to_markdown
from .uninstall import launch_uninstaller
from .wizard import SetupWizard

CONSENT = (
    "Tell everyone on the call that you are recording, and make sure that is allowed where "
    "you and they live and by your meeting platform.\n\n"
    "Audio stays on this computer. Start recording?"
)
EMPTY_HINT = (
    "Press Record, then carry on with your call. Captions appear here while you talk.\n\n"
    "Pick an earlier recording on the left to read, play or rename it."
)
log = logging.getLogger("ilfu")
LINE = re.compile(r"\*\*\[(?P<t>[^\]]+)\]\*\* (?:(?P<who>You|Them): )?(?P<text>.*)")


class App:
    def __init__(self, root: tk.Tk, backend: str = "auto", cfg: Config | None = None) -> None:
        self.root = root
        self.backend_name = backend
        self.cfg = cfg or load()
        self.recorder: Recorder | None = None
        self.live: LiveTranscriber | None = None
        self.session_dir: Path | None = None
        self.transcriber = None
        self.busy = False  # finishing a recording or re-transcribing
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.shown: Path | None = None
        self.sessions: dict[str, library.SessionInfo] = {}
        self.record_seconds = 0.0
        self.resumed_at = 0.0
        self.paused = False

        root.title(f"I-L-F-U Call Transcriber {__version__}")
        root.geometry("1040x660")
        root.minsize(820, 520)
        ui.apply_style(root)
        self._build_menu()
        self._build_body()
        root.protocol("WM_DELETE_WINDOW", self.quit)
        self.refresh_list()
        self._load_model_async()
        self._poll()
        self._tick()

    # ---- layout ----
    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Open recordings folder", command=self.open_folder)
        file_menu.add_command(label="Save transcript as...", command=self.save_as)
        file_menu.add_command(label="Setup and settings...", command=self.run_setup)
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self.quit)
        menubar.add_cascade(label="File", menu=file_menu)
        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="About", command=self.about)
        help_menu.add_command(label="Uninstall...", command=self.uninstall)
        menubar.add_cascade(label="Help", menu=help_menu)
        self.root.config(menu=menubar)

    def _build_body(self) -> None:
        root = self.root
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        # left: history
        side = ttk.Frame(root, style="Panel.TFrame", padding=(14, 14, 14, 10), width=330)
        side.grid(row=0, column=0, sticky="ns")
        side.grid_propagate(False)
        side.rowconfigure(1, weight=1)
        side.columnconfigure(0, weight=1)
        ttk.Label(side, text="Recordings", style="Heading.TLabel", background=ui.PANEL).grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        self.tree = ttk.Treeview(side, columns=("len",), show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="Call")
        self.tree.heading("len", text="Length")
        self.tree.column("#0", width=190, stretch=True)
        self.tree.column("len", width=60, anchor="e", stretch=False)
        self.tree.grid(row=1, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self.on_select())
        self.tree.bind("<Double-1>", lambda _e: self.rename())
        self.tree.bind("<Delete>", lambda _e: self.delete())
        actions = ttk.Frame(side, style="Panel.TFrame")
        actions.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self.rename_btn = ttk.Button(actions, text="Rename", command=self.rename, padding=(8, 6))
        self.rename_btn.pack(side="left")
        self.delete_btn = ttk.Button(actions, text="Delete", command=self.delete, padding=(8, 6))
        self.delete_btn.pack(side="left", padx=6)
        ttk.Button(actions, text="Open folder", command=self.open_folder, padding=(8, 6)).pack(
            side="left"
        )

        # right: controls and transcript
        main = ttk.Frame(root, padding=(18, 14))
        main.grid(row=0, column=1, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(2, weight=1)

        bar = ttk.Frame(main)
        bar.grid(row=0, column=0, sticky="ew")
        self.record_btn = ttk.Button(
            bar, text="●  Record", style="Record.TButton", command=self.toggle
        )
        self.record_btn.pack(side="left")
        self.pause_btn = ttk.Button(bar, text="Pause", command=self.toggle_pause, state="disabled")
        self.pause_btn.pack(side="left", padx=8)
        self.timer = ttk.Label(bar, text="00:00", style="Timer.TLabel")
        self.timer.pack(side="left", padx=12)
        self.language = tk.StringVar(value=LANGUAGES.get(self.cfg.language, LANGUAGES["auto"]))

        info = ttk.Frame(main)
        info.grid(row=1, column=0, sticky="ew")
        self.status = ttk.Label(info, text="Ready", style="Muted.TLabel", padding=(0, 8))
        self.status.pack(side="left", fill="x", expand=True)
        lang = ttk.Combobox(
            info, textvariable=self.language, values=list(LANGUAGES.values()),
            state="readonly", width=24,
        )
        lang.pack(side="right")
        lang.bind("<<ComboboxSelected>>", lambda _e: self.on_language())
        ttk.Label(info, text="Language:", style="Muted.TLabel").pack(side="right", padx=(8, 6))

        frame = ttk.Frame(main, style="Panel.TFrame", padding=1)
        frame.grid(row=2, column=0, sticky="nsew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.text = tk.Text(
            frame, wrap="word", font=(ui.FONT, 11), relief="flat", background=ui.PANEL,
            padx=16, pady=12, spacing3=8, borderwidth=0, highlightthickness=0,
        )
        scroll = ttk.Scrollbar(frame, command=self.text.yview)
        self.text.config(yscrollcommand=scroll.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.text.tag_config("time", foreground=ui.MUTED, font=(ui.FONT, 9))
        self.text.tag_config("You", foreground=ui.YOU, font=(ui.FONT, 11, "bold"))
        self.text.tag_config("Them", foreground=ui.THEM, font=(ui.FONT, 11, "bold"))
        self.text.tag_config("hint", foreground=ui.MUTED)
        self._show_hint()

        foot = ttk.Frame(main, padding=(0, 10, 0, 0))
        foot.grid(row=3, column=0, sticky="ew")
        pad = (10, 6)
        self.play_btn = ttk.Button(foot, text="▶  Play", command=self.play, padding=pad)
        self.play_btn.pack(side="left")
        self.stop_play_btn = ttk.Button(foot, text="Stop", command=playback.stop, padding=pad)
        self.stop_play_btn.pack(side="left", padx=6)
        self.retranscribe_btn = ttk.Button(
            foot, text="Re-transcribe", command=self.retranscribe, padding=pad
        )
        self.retranscribe_btn.pack(side="left")
        ttk.Button(foot, text="Copy", command=self.copy_text, padding=pad).pack(side="right")
        ttk.Button(foot, text="Save as...", command=self.save_as, padding=pad).pack(
            side="right", padx=6
        )
        self._sync_buttons()

    # ---- transcript view ----
    def _show_hint(self) -> None:
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", EMPTY_HINT, "hint")
        self.text.config(state="disabled")

    def _clear_text(self) -> None:
        self.text.config(state="normal")
        self.text.delete("1.0", "end")

    def _append(self, stamp: str, who: str | None, text: str) -> None:
        self.text.config(state="normal")
        self.text.insert("end", f"{stamp}  ", "time")
        if who:
            self.text.insert("end", f"{who}  ", who)
        self.text.insert("end", text + "\n")
        self.text.see("end")
        self.text.config(state="disabled")

    def _render_markdown(self, markdown: str) -> None:
        self._clear_text()
        self.text.config(state="disabled")
        for line in markdown.splitlines():
            if not line.strip():
                continue
            m = LINE.match(line)
            if m:
                self._append(m["t"], m["who"], m["text"])
            else:
                self._append("", None, line)
        self.text.yview_moveto(0)

    @staticmethod
    def _stamp(seconds: float) -> str:
        return time.strftime("%H:%M:%S", time.gmtime(seconds))

    # ---- history ----
    def refresh_list(self, select: Path | None = None) -> None:
        self.sessions = {}
        for item in self.tree.get_children():
            self.tree.delete(item)
        for info in library.list_sessions(self.cfg.sessions_dir()):
            iid = str(info.path)
            self.sessions[iid] = info
            self.tree.insert("", "end", iid=iid, text=info.title,
                             values=(library.format_duration(info.duration),))
        if select and str(select) in self.sessions:
            self.tree.selection_set(str(select))
        else:
            self._sync_buttons()

    def selected(self) -> library.SessionInfo | None:
        sel = self.tree.selection()
        return self.sessions.get(sel[0]) if sel else None

    def on_select(self) -> None:
        info = self.selected()
        self._sync_buttons()
        if info is None or self.recorder is not None or self.busy:
            return
        self.shown = info.path
        text = library.read_transcript(info.path)
        if text:
            self._render_markdown(text)
        else:
            self._clear_text()
            self.text.insert("1.0", "No transcript yet. Use Re-transcribe.", "hint")
            self.text.config(state="disabled")
        self._set_status(f"{info.created}  |  {library.format_duration(info.duration)} long")

    def rename(self) -> None:
        info = self.selected()
        if info is None or self.recorder is not None:
            return
        title = simpledialog.askstring("Rename", "New name:", initialvalue=info.title,
                                       parent=self.root)
        if title and title.strip():
            library.rename(info.path, title)
            self.refresh_list(select=info.path)

    def delete(self) -> None:
        info = self.selected()
        if info is None or self.recorder is not None or self.busy:
            return
        if not messagebox.askyesno(
            "Delete recording",
            f"Delete \"{info.title}\" with its audio and transcript?\n\nThis cannot be undone.",
            icon="warning", default="no", parent=self.root,
        ):
            return
        try:
            library.delete(info.path)
        except OSError as exc:
            messagebox.showerror("Could not delete", str(exc), parent=self.root)
            return
        self.shown = None
        self._show_hint()
        self.refresh_list()
        self._set_status("Deleted")

    # ---- model ----
    def _load_model_async(self) -> None:
        if not self.cfg.model or not models.is_downloaded(self.cfg.model):
            self._set_status("Speech model not set up. Open File > Setup and settings.")
            return
        self._set_status("Loading the speech model...")

        def work() -> None:
            try:
                from .transcribe import FasterWhisperTranscriber

                tier = choose_tier(detect_hardware())
                self.transcriber = FasterWhisperTranscriber(
                    tier, self.cfg.language_code(), model=self.cfg.model, beam_size=1
                )
                self.events.put(("model", None))
            except Exception as exc:  # noqa: BLE001 - shown in the window
                self.events.put(("model_error", str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def on_language(self) -> None:
        label = self.language.get()
        self.cfg.language = next((c for c, n in LANGUAGES.items() if n == label), "auto")
        save(self.cfg)
        if self.transcriber is not None:
            self.transcriber.language = self.cfg.language_code()

    # ---- recording ----
    def toggle(self) -> None:
        if self.busy:
            return
        if self.recorder is None:
            self.start()
        else:
            self.stop()

    def start(self) -> None:
        if not self.cfg.model:
            messagebox.showinfo("Setup needed", "Finish the setup first.", parent=self.root)
            self.run_setup()
            return
        if not messagebox.askokcancel("Recording consent", CONSENT, parent=self.root):
            return
        try:
            backend = get_backend(self.backend_name)
            self.session_dir = new_session_dir(self.cfg.sessions_dir())
            self.recorder = Recorder(
                {"system": backend.open_system_audio(), "mic": backend.open_microphone()},
                self.session_dir,
            )
            self.live = LiveTranscriber(
                self.recorder,
                lambda: self.transcriber,
                lambda segs: self.events.put(("segments", segs)),
                lambda msg: self.events.put(("live_error", msg)),
            )
            self.recorder.start()
            self.live.start()
        except Exception as exc:  # noqa: BLE001 - show any device problem in plain words
            self.recorder = None
            self.live = None
            messagebox.showerror("Could not start recording", str(exc), parent=self.root)
            return
        self.record_seconds = 0.0
        self.resumed_at = time.time()
        self.paused = False
        self._clear_text()
        self.text.config(state="disabled")
        self.shown = None
        self.record_btn.config(text="■  Stop")
        self.pause_btn.config(text="Pause", state="normal")
        self._sync_buttons()
        self._set_status("Recording. You can switch back to your call.")

    def toggle_pause(self) -> None:
        if self.recorder is None:
            return
        if self.paused:
            self.recorder.resume()
            self.resumed_at = time.time()
            self.paused = False
            self.pause_btn.config(text="Pause")
            self._set_status("Recording.")
        else:
            self.recorder.pause()
            self.record_seconds += time.time() - self.resumed_at
            self.paused = True
            self.pause_btn.config(text="Resume")
            self._set_status("Paused. Nothing is being recorded.")

    def stop(self) -> None:
        recorder, live, session = self.recorder, self.live, self.session_dir
        if recorder is None or live is None or session is None:
            return
        if not self.paused:
            self.record_seconds += time.time() - self.resumed_at
        self.recorder = None
        self.live = None
        self.busy = True
        self.record_btn.config(text="●  Record", state="disabled")
        self.pause_btn.config(state="disabled")
        self._set_status("Finishing the last captions...")
        duration = self.record_seconds

        def work() -> None:
            try:
                recorder.stop()
                segments = live.stop()
                markdown = to_markdown(segments) if segments else ""
                if markdown:
                    (session / "transcript.md").write_text(markdown, encoding="utf-8")
                library.write_meta(
                    session, duration=round(duration, 1), language=self.cfg.language,
                    model=self.cfg.model, failed=live.failed,
                )
                self.events.put(("stopped", session))
            except Exception as exc:  # noqa: BLE001 - never crash the window
                self.events.put(("error", str(exc)))

        threading.Thread(target=work, daemon=True).start()

    # ---- playback and re-transcription ----
    def play(self) -> None:
        info = self.selected()
        if info is None:
            return
        try:
            path = playback.mixed_file(info.path)
            if path is None:
                messagebox.showinfo("Nothing to play", "This recording has no audio.",
                                    parent=self.root)
                return
            playback.play(path)
            self._set_status("Playing... use Stop playback to stop")
        except Exception as exc:  # noqa: BLE001 - shown in plain words
            messagebox.showerror("Could not play", str(exc), parent=self.root)

    def retranscribe(self) -> None:
        info = self.selected()
        if info is None or self.recorder is not None or self.busy:
            return
        if self.transcriber is None:
            messagebox.showinfo("Please wait", "The speech model is still loading.",
                                parent=self.root)
            return
        self.busy = True
        self._sync_buttons()
        self._set_status("Re-transcribing with full accuracy. This takes a while for long calls.")
        transcriber = self.transcriber

        def work() -> None:
            try:
                transcriber.beam_size = 5
                segments = transcribe_session(info.path, transcriber)
                markdown = to_markdown(segments) if segments else "(No speech found.)\n"
                (info.path / "transcript.md").write_text(markdown, encoding="utf-8")
                self.events.put(("stopped", info.path))
            except Exception as exc:  # noqa: BLE001
                self.events.put(("error", str(exc)))
            finally:
                transcriber.beam_size = 1

        threading.Thread(target=work, daemon=True).start()

    # ---- menu actions ----
    def open_folder(self) -> None:
        folder = self.cfg.sessions_dir()
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(folder)  # type: ignore[attr-defined]
        else:
            messagebox.showinfo("Recordings folder", str(folder), parent=self.root)

    def _current_markdown(self) -> str:
        info = self.selected()
        return library.read_transcript(info.path) if info else ""

    def save_as(self) -> None:
        markdown = self._current_markdown()
        if not markdown:
            messagebox.showinfo("Nothing to save", "Select a recording with a transcript.",
                                parent=self.root)
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".md", filetypes=[("Markdown", "*.md"), ("Text", "*.txt")]
        )
        if path:
            Path(path).write_text(markdown, encoding="utf-8")

    def copy_text(self) -> None:
        text = self.text.get("1.0", "end").strip()
        if text:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self._set_status("Copied to the clipboard")

    def run_setup(self) -> None:
        if self.recorder is not None or self.busy:
            messagebox.showinfo("Busy", "Finish the current recording first.", parent=self.root)
            return
        win = tk.Toplevel(self.root)
        win.title("Setup and settings")
        win.geometry("760x640")
        win.transient(self.root)
        win.grab_set()
        ui.apply_style(win)

        def done(cfg: Config) -> None:
            self.cfg = cfg
            self.language.set(LANGUAGES.get(cfg.language, LANGUAGES["auto"]))
            self.transcriber = None
            win.destroy()
            self.refresh_list()
            self._load_model_async()

        SetupWizard(win, Config(**vars(self.cfg)), done)

    def about(self) -> None:
        messagebox.showinfo(
            "About",
            f"I-L-F-U Call Transcriber {__version__}\n"
            "Free, open source (AGPL-3.0). Audio never leaves your computer.\n"
            "https://github.com/myviapps/I-L-F-U\n\nProblems are logged in ilfu.log inside the "
            "install folder.",
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
            if not messagebox.askyesno(
                "Recording in progress",
                "A recording is running. Stop it and keep the audio?",
                parent=self.root,
            ):
                return
            with contextlib.suppress(Exception):
                self.recorder.stop()
            if self.session_dir is not None:
                with contextlib.suppress(Exception):
                    library.write_meta(self.session_dir, duration=round(self.record_seconds, 1))
            self.recorder = None
        playback.stop()
        self.root.destroy()

    # ---- state ----
    def _sync_buttons(self) -> None:
        has = self.selected() is not None
        idle = self.recorder is None and not self.busy
        state = "normal" if has and idle else "disabled"
        for btn in (self.rename_btn, self.delete_btn, self.play_btn, self.retranscribe_btn):
            btn.config(state=state)
        self.stop_play_btn.config(state="normal" if playback.supported() else "disabled")
        if not playback.supported():
            self.play_btn.config(state="disabled")

    def _set_status(self, text: str) -> None:
        self.status.config(text=text)

    def _tick(self) -> None:
        if self.recorder is not None:
            seconds = self.record_seconds + (0 if self.paused else time.time() - self.resumed_at)
            self.timer.config(text=library.format_duration(seconds))
            if self.live is not None and not self.paused:
                lag = self.live.lag_seconds()
                if self.transcriber is None:
                    self._set_status("Recording. Captions start when the speech model is loaded.")
                elif lag > 15:
                    self._set_status(
                        f"Recording. Captions are about {int(lag)} s behind. "
                        "A smaller model keeps up better."
                    )
        self.root.after(500, self._tick)

    def _poll(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                self._handle(kind, payload)
        except queue.Empty:
            pass
        self.root.after(150, self._poll)

    def _handle(self, kind: str, payload: object) -> None:
        if kind in ("model_error", "live_error", "error"):
            log.error("%s: %s", kind, payload)
        if kind == "segments":
            if self.recorder is not None:
                for seg in payload:  # type: ignore[attr-defined]
                    self._append(self._stamp(seg.start), seg.speaker, seg.text)
        elif kind == "stopped":
            self.busy = False
            self.record_btn.config(state="normal")
            self.timer.config(text="00:00")
            self.refresh_list(select=payload)  # type: ignore[arg-type]
            self.on_select()
        elif kind == "model":
            self._set_status("Ready")
        elif kind == "model_error":
            self._set_status("The speech model could not be loaded")
            messagebox.showerror("Speech model", str(payload), parent=self.root)
        elif kind == "live_error":
            self._set_status("Live captions stopped. The recording continues; re-transcribe later.")
        else:
            self.busy = False
            self.record_btn.config(state="normal")
            self._sync_buttons()
            self._set_status("Something went wrong")
            messagebox.showerror("Error", str(payload), parent=self.root)


def _setup_log() -> Path:
    """pythonw shows no console, so errors go to a file the user can send us."""
    from .config import config_path

    path = config_path().with_name("ilfu.log")
    path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=path, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    log.info("I-L-F-U %s starting on %s", __version__, sys.platform)
    return path


def main(backend: str = "auto") -> int:
    ui.make_dpi_aware()
    with contextlib.suppress(OSError):
        _setup_log()
    root = tk.Tk()
    root.report_callback_exception = lambda *exc: log.error("window error", exc_info=exc)
    cfg = load()
    if needs_setup(cfg) or not models.is_downloaded(cfg.model):
        root.title("I-L-F-U Setup")
        root.geometry("760x640")
        ui.apply_style(root)

        def done(new_cfg: Config) -> None:
            for child in root.winfo_children():
                child.destroy()
            App(root, backend, new_cfg)

        SetupWizard(root, cfg, done)
    else:
        App(root, backend, cfg)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
