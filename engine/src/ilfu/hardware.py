"""Detect the machine and pick a model tier, so setup needs no decisions from the user."""

from __future__ import annotations

import ctypes
import os
import shutil
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Hardware:
    cpu_cores: int
    ram_gb: float
    has_cuda: bool


@dataclass(frozen=True)
class Tier:
    name: str
    model: str
    compute_type: str
    device: str
    live_captions: bool


def _ram_gb() -> float:
    if sys.platform == "win32":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("load", ctypes.c_ulong),
                ("total_phys", ctypes.c_ulonglong),
                ("avail_phys", ctypes.c_ulonglong),
                ("total_page", ctypes.c_ulonglong),
                ("avail_page", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("avail_virtual", ctypes.c_ulonglong),
                ("avail_ext", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(MemoryStatus)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))  # type: ignore[attr-defined]
        return status.total_phys / 1024**3
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024**3
    except (ValueError, OSError, AttributeError):
        return 0.0


def detect_hardware() -> Hardware:
    return Hardware(
        cpu_cores=os.cpu_count() or 1,
        ram_gb=round(_ram_gb(), 1),
        has_cuda=shutil.which("nvidia-smi") is not None,
    )


def choose_tier(hw: Hardware) -> Tier:
    """Pick the biggest model the machine can run comfortably.

    Thresholds are first guesses; they must be measured on real low-spec machines
    (see Phase 1 and 2 in docs/ROADMAP.md).
    """
    if hw.has_cuda and hw.ram_gb >= 8:
        return Tier("standard", "large-v3-turbo", "float16", "cuda", live_captions=True)
    if hw.cpu_cores >= 8 and hw.ram_gb >= 16:
        return Tier("standard", "large-v3-turbo", "int8", "cpu", live_captions=False)
    if hw.cpu_cores >= 4 and hw.ram_gb >= 8:
        return Tier("light", "small", "int8", "cpu", live_captions=True)
    return Tier("minimal", "base", "int8", "cpu", live_captions=False)
