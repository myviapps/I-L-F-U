"""First-run setup: agreement, where to save, language and model, and the model download.

Everything the app needs is in place before the main window opens, so recording never waits
for a download.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from . import models, ui
from .config import LANGUAGES, TERMS_VERSION, Config, default_save_dir, save
from .hardware import detect_hardware
from .terms import TERMS

STEPS = ["Welcome", "Save location", "Language and model", "Download"]


def _writable(folder: Path) -> str | None:
    """Return None when the folder can be used, otherwise a plain-words problem."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".ilfu-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return f"Cannot write to that folder: {exc}"
    return None


class SetupWizard(ttk.Frame):
    def __init__(self, root: tk.Misc, cfg: Config, on_done: Callable[[Config], None]) -> None:
        super().__init__(root, padding=0)
        self.cfg = cfg
        self.on_done = on_done
        self.step = 0
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        hw = detect_hardware()
        self.recommended = models.recommended(hw.cpu_cores, hw.ram_gb, hw.has_cuda)
        self.hw_text = f"{hw.cpu_cores} CPU cores, {hw.ram_gb:g} GB memory" + (
            ", NVIDIA graphics card" if hw.has_cuda else ""
        )

        self.agree = tk.BooleanVar(value=cfg.terms_version >= TERMS_VERSION)
        self.folder = tk.StringVar(value=cfg.save_dir or str(default_save_dir()))
        self.language = tk.StringVar(value=LANGUAGES.get(cfg.language, LANGUAGES["auto"]))
        self.model = tk.StringVar(value=cfg.model or self.recommended)
        self.progress = tk.DoubleVar(value=0)
        self.downloading = False
        self.download_ok = False

        self.header = ttk.Label(self, text="", style="Title.TLabel", padding=(28, 22, 28, 0))
        self.header.pack(fill="x")
        self.sub = ttk.Label(self, text="", style="Muted.TLabel", padding=(28, 2, 28, 10))
        self.sub.pack(fill="x")
        self.body = ttk.Frame(self, padding=(28, 0))
        self.body.pack(fill="both", expand=True)
        bar = ttk.Frame(self, padding=(28, 14))
        bar.pack(fill="x")
        self.back_btn = ttk.Button(bar, text="Back", command=self.back)
        self.back_btn.pack(side="left")
        self.cancel_btn = ttk.Button(bar, text="Cancel", command=self.cancel)
        self.cancel_btn.pack(side="left", padx=8)
        self.next_btn = ttk.Button(bar, text="Next", style="Accent.TButton", command=self.next)
        self.next_btn.pack(side="right")
        self.pack(fill="both", expand=True)
        self._after_id: str | None = None
        self.bind("<Destroy>", self._on_destroy)
        self._show()
        self._poll()

    def _on_destroy(self, event: tk.Event) -> None:
        if event.widget is self and self._after_id:
            self.after_cancel(self._after_id)

    # ---- navigation ----
    def _clear(self) -> None:
        for child in self.body.winfo_children():
            child.destroy()

    def _show(self) -> None:
        self._clear()
        self.header.config(text=STEPS[self.step])
        self.sub.config(text=f"Step {self.step + 1} of {len(STEPS)}")
        self.back_btn.config(state="normal" if self.step > 0 and not self.downloading else "disabled")
        self.next_btn.config(text="Next", state="normal")
        [self._page_welcome, self._page_folder, self._page_model, self._page_download][self.step]()

    def back(self) -> None:
        if self.step > 0:
            self.step -= 1
            self._show()

    def cancel(self) -> None:
        if self.downloading and not messagebox.askyesno(
            "Cancel setup", "The download is still running. Cancel setup?", parent=self
        ):
            return
        self.winfo_toplevel().destroy()

    def next(self) -> None:
        if self.step == 0 and not self.agree.get():
            return
        if self.step == 1:
            problem = _writable(Path(self.folder.get()))
            if problem:
                messagebox.showerror("Save location", problem, parent=self)
                return
        if self.step == 2:
            self.cfg.language = self._language_code()
            self.cfg.model = self.model.get()
        if self.step == len(STEPS) - 1:
            self._finish()
            return
        self.step += 1
        self._show()

    def _finish(self) -> None:
        self.cfg.terms_version = TERMS_VERSION
        self.cfg.save_dir = self.folder.get()
        self.cfg.setup_done = True
        save(self.cfg)
        self.pack_forget()
        self.destroy()
        self.on_done(self.cfg)

    # ---- pages ----
    def _page_welcome(self) -> None:
        ttk.Label(
            self.body,
            text="Record your online calls and get a written transcript. Everything runs on "
            "this computer. No account, no key, no upload.\nPlease read and accept the "
            "agreement to continue.",
            wraplength=640, justify="left",
        ).pack(fill="x", pady=(0, 10))
        box = scrolledtext.ScrolledText(
            self.body, wrap="word", height=12, font=(ui.FONT, 10), relief="flat",
            background=ui.PANEL, padx=12, pady=10,
        )
        box.insert("1.0", TERMS)
        box.config(state="disabled")
        box.pack(fill="both", expand=True)
        ttk.Checkbutton(
            self.body, text="I have read the agreement and I accept it", variable=self.agree,
            command=self._sync_next,
        ).pack(anchor="w", pady=10)
        self._sync_next()

    def _sync_next(self) -> None:
        if self.step == 0:
            self.next_btn.config(state="normal" if self.agree.get() else "disabled")

    def _page_folder(self) -> None:
        ttk.Label(
            self.body,
            text="Choose where recordings and transcripts are saved. Each call gets its own "
            "folder inside it.",
            wraplength=640, justify="left",
        ).pack(fill="x", pady=(0, 14))
        row = ttk.Frame(self.body)
        row.pack(fill="x")
        ttk.Entry(row, textvariable=self.folder, font=(ui.FONT, 10)).pack(
            side="left", fill="x", expand=True, ipady=4
        )
        ttk.Button(row, text="Browse...", command=self._browse).pack(side="left", padx=(8, 0))
        ttk.Label(
            self.body, style="Muted.TLabel", wraplength=640, justify="left",
            text="Audio takes roughly 60 MB per hour per track. Choose a drive with free space. "
            "You can change this later in File > Settings.",
        ).pack(fill="x", pady=12)

    def _browse(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.folder.get(), parent=self)
        if chosen:
            self.folder.set(str(Path(chosen)))

    def _language_code(self) -> str:
        label = self.language.get()
        return next((code for code, name in LANGUAGES.items() if name == label), "auto")

    def _page_model(self) -> None:
        ttk.Label(self.body, text="Language you will mostly hear").pack(anchor="w")
        combo = ttk.Combobox(
            self.body, textvariable=self.language, values=list(LANGUAGES.values()),
            state="readonly", width=34,
        )
        combo.pack(anchor="w", pady=(2, 4))
        self.lang_hint = ttk.Label(self.body, style="Muted.TLabel", wraplength=640, justify="left")
        self.lang_hint.pack(fill="x", pady=(0, 10))
        combo.bind("<<ComboboxSelected>>", lambda _e: self._update_hint())
        ttk.Label(self.body, text="Speech model (downloaded once, stays on this computer)").pack(
            anchor="w"
        )
        panel = ttk.Frame(self.body, style="Panel.TFrame", padding=10)
        panel.pack(fill="x", pady=(4, 0))
        for meta in models.MODELS:
            mark = "  (recommended for this computer)" if meta.name == self.recommended else ""
            ttk.Radiobutton(
                panel, variable=self.model, value=meta.name,
                text=f"{meta.label}, {meta.size_mb} MB{mark}",
            ).pack(anchor="w", pady=(6, 0))
            ttk.Label(panel, text=meta.note, style="Panel.TLabel", foreground=ui.MUTED,
                      wraplength=600, justify="left").pack(anchor="w", padx=(24, 0))
        ttk.Label(self.body, style="Muted.TLabel", text=f"This computer: {self.hw_text}").pack(
            anchor="w", pady=8
        )
        self._update_hint()

    def _update_hint(self) -> None:
        code = self._language_code()
        if code in ("en", "auto"):
            text = "English works well with every model."
        else:
            text = ("Accuracy for this language is much lower with the Fast model. Choose "
                    "Accurate or Best if your computer can handle it. Check important words.")
        self.lang_hint.config(text=text)

    def _page_download(self) -> None:
        meta = models.info(self.cfg.model)
        self.download_ok = models.is_downloaded(meta.name)
        ttk.Label(
            self.body, wraplength=640, justify="left",
            text=f"The {meta.label} speech model ({meta.size_mb} MB) is needed before you can "
            "record. This is the only time the app uses the internet.",
        ).pack(fill="x", pady=(0, 16))
        ttk.Progressbar(self.body, variable=self.progress, maximum=1.0, length=500).pack(
            fill="x"
        )
        self.dl_status = ttk.Label(self.body, text="", style="Muted.TLabel")
        self.dl_status.pack(anchor="w", pady=8)
        self.retry_btn = ttk.Button(self.body, text="Try again", command=self._start_download)
        if self.download_ok:
            self.progress.set(1)
            self._download_finished()
        else:
            self._start_download()

    def _start_download(self) -> None:
        if self.downloading:
            return
        self.downloading = True
        self.retry_btn.pack_forget()
        self.next_btn.config(state="disabled")
        self.back_btn.config(state="disabled")
        self.dl_status.config(text="Downloading... you can leave this window open")
        name = self.cfg.model

        def work() -> None:
            try:
                models.download(name, lambda f: self.events.put(("progress", f)))
                self.events.put(("done", None))
            except Exception as exc:  # noqa: BLE001 - shown to the user with a retry button
                self.events.put(("error", str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def _download_finished(self) -> None:
        self.downloading = False
        self.download_ok = True
        self.dl_status.config(text="Ready. The model is on this computer.")
        self.next_btn.config(text="Finish", state="normal")
        self.back_btn.config(state="normal")

    def _poll(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if not self.winfo_exists() or self.step != len(STEPS) - 1:
                    continue
                if kind == "progress":
                    self.progress.set(float(payload))  # type: ignore[arg-type]
                    self.dl_status.config(text=f"Downloading... {float(payload):.0%}")  # type: ignore[arg-type]
                elif kind == "done":
                    self.progress.set(1)
                    self._download_finished()
                else:
                    self.downloading = False
                    self.dl_status.config(text=f"Download failed: {payload}")
                    self.retry_btn.pack(anchor="w")
                    self.back_btn.config(state="normal")
        except queue.Empty:
            pass
        except tk.TclError:
            return
        if self.winfo_exists():
            self._after_id = self.after(200, self._poll)
