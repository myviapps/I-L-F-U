"""Shared look for every window: colours, fonts and ttk styles."""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk

BG = "#f4f5f7"
PANEL = "#ffffff"
TEXT = "#1f2937"
MUTED = "#6b7280"
ACCENT = "#2563eb"
ACCENT_DARK = "#1d4ed8"
RECORD = "#dc2626"
RECORD_DARK = "#b91c1c"
BORDER = "#e5e7eb"
YOU = "#1d4ed8"
THEM = "#047857"

FONT = "Segoe UI" if sys.platform == "win32" else "TkDefaultFont"


def make_dpi_aware() -> None:
    """Without this Windows scales the window as a blurry bitmap on high-resolution screens."""
    if sys.platform != "win32":
        return
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass


def apply_style(root: tk.Misc) -> None:
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    root.configure(background=BG)
    style.configure(".", background=BG, foreground=TEXT, font=(FONT, 10))
    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Panel.TLabel", background=PANEL)
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("Title.TLabel", font=(FONT, 20, "bold"))
    style.configure("Heading.TLabel", font=(FONT, 12, "bold"))
    style.configure("Timer.TLabel", font=(FONT, 22, "bold"))
    style.configure("TButton", padding=(12, 7), borderwidth=0, background="#e5e7eb")
    style.map("TButton", background=[("active", "#d1d5db"), ("disabled", "#eef0f3")],
              foreground=[("disabled", "#9ca3af")])
    style.configure("Accent.TButton", background=ACCENT, foreground="white",
                    font=(FONT, 10, "bold"))
    style.map("Accent.TButton", background=[("active", ACCENT_DARK), ("disabled", "#93b4f5")],
              foreground=[("disabled", "#eef2ff")])
    style.configure("Record.TButton", background=RECORD, foreground="white", padding=(18, 10),
                    font=(FONT, 12, "bold"))
    style.map("Record.TButton", background=[("active", RECORD_DARK), ("disabled", "#f3a8a8")],
              foreground=[("disabled", "#fff1f1")])
    style.configure("TCheckbutton", background=BG)
    style.configure("TRadiobutton", background=PANEL)
    style.configure("Treeview", background=PANEL, fieldbackground=PANEL, rowheight=30,
                    borderwidth=0, font=(FONT, 10))
    style.configure("Treeview.Heading", font=(FONT, 9, "bold"), background=BG, relief="flat")
    style.map("Treeview", background=[("selected", "#dbeafe")], foreground=[("selected", TEXT)])
    style.configure("Horizontal.TProgressbar", troughcolor=BORDER, background=ACCENT,
                    thickness=14, borderwidth=0)
