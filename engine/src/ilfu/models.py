"""Speech models: which ones exist, whether they are on this computer, and downloading them."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .paths import model_dir

COMPLETE_MARKER = ".complete"
_FILES = ["config.json", "preprocessor_config.json", "model.bin", "tokenizer.json", "vocabulary.*"]


@dataclass(frozen=True)
class ModelInfo:
    name: str
    label: str
    size_mb: int  # approximate download size
    repo: str
    note: str


MODELS = (
    ModelInfo("base", "Fast", 145, "Systran/faster-whisper-base",
              "Smallest and quickest. Fine for clear English; weak for most other languages."),
    ModelInfo("small", "Balanced", 485, "Systran/faster-whisper-small",
              "Good all-round choice. Keeps up with live captions on most laptops."),
    ModelInfo("medium", "Accurate", 1530, "Systran/faster-whisper-medium",
              "Noticeably better for Hindi, Telugu and other languages. Needs 8 GB RAM or more; "
              "live captions may lag on a slow processor."),
    ModelInfo("large-v3-turbo", "Best", 1620, "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
              "Most accurate. Needs a strong processor or a graphics card for live captions."),
)


def info(name: str) -> ModelInfo:
    for model in MODELS:
        if model.name == name:
            return model
    raise KeyError(f"Unknown model: {name}")


def models_root() -> Path:
    return model_dir() or Path.home() / ".ilfu" / "models"


def model_path(name: str) -> Path:
    return models_root() / name


def is_downloaded(name: str) -> bool:
    return (model_path(name) / COMPLETE_MARKER).exists()


def _folder_bytes(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            pass
    return total


def _hub_fetch(repo: str, target: Path) -> None:
    from huggingface_hub import snapshot_download

    snapshot_download(repo, local_dir=str(target), allow_patterns=_FILES)


def download(
    name: str,
    progress: Callable[[float], None] | None = None,
    fetch: Callable[[str, Path], None] | None = None,
) -> Path:
    """Download a model into the install folder. `progress` gets a number from 0 to 1.

    Progress is estimated from the size of the folder, because the download library does not
    report one number for a multi-file download. Resumes if interrupted.
    """
    meta = info(name)
    target = model_path(name)
    target.mkdir(parents=True, exist_ok=True)
    expected = meta.size_mb * 1024 * 1024
    stop = threading.Event()

    def watch() -> None:
        while not stop.wait(0.4):
            if progress:
                progress(min(_folder_bytes(target) / expected, 0.99))

    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()
    try:
        (fetch or _hub_fetch)(meta.repo, target)
    finally:
        stop.set()
        watcher.join()
    (target / COMPLETE_MARKER).write_text(meta.repo, encoding="utf-8")
    if progress:
        progress(1.0)
    return target


def remove(name: str) -> None:
    import shutil

    shutil.rmtree(model_path(name), ignore_errors=True)


def recommended(cpu_cores: int, ram_gb: float, has_cuda: bool) -> str:
    """The model that should keep up with live captions on this computer."""
    if has_cuda and ram_gb >= 8:
        return "large-v3-turbo"
    if cpu_cores >= 4 and ram_gb >= 8:
        return "small"
    return "base"
