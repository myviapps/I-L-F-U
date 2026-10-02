"""The user's saved choices: agreement, save folder, speech model and language."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from .paths import documents_dir, install_home

# Bump when the agreement text changes, so everyone is asked to accept it again.
TERMS_VERSION = 1

# Languages Whisper can transcribe. Quality differs a lot between them; see docs/LANGUAGES.md.
LANGUAGES = {
    "auto": "Detect automatically",
    "en": "English",
    "hi": "Hindi (हिन्दी)",
    "te": "Telugu (తెలుగు)",
    "ta": "Tamil (தமிழ்)",
    "kn": "Kannada (ಕನ್ನಡ)",
    "ml": "Malayalam (മലയാളം)",
    "mr": "Marathi (मराठी)",
    "bn": "Bengali (বাংলা)",
    "gu": "Gujarati (ગુજરાતી)",
    "pa": "Punjabi (ਪੰਜਾਬੀ)",
    "ur": "Urdu (اردو)",
    "ne": "Nepali (नेपाली)",
    "es": "Spanish (Español)",
    "fr": "French (Français)",
    "de": "German (Deutsch)",
    "pt": "Portuguese (Português)",
    "it": "Italian (Italiano)",
    "nl": "Dutch (Nederlands)",
    "ru": "Russian (Русский)",
    "ar": "Arabic (العربية)",
    "tr": "Turkish (Türkçe)",
    "id": "Indonesian (Bahasa Indonesia)",
    "vi": "Vietnamese (Tiếng Việt)",
    "th": "Thai (ไทย)",
    "zh": "Chinese (中文)",
    "ja": "Japanese (日本語)",
    "ko": "Korean (한국어)",
}


@dataclass
class Config:
    terms_version: int = 0
    setup_done: bool = False
    save_dir: str = ""
    model: str = ""  # a model name from models.MODELS, empty until chosen
    language: str = "auto"

    def language_code(self) -> str | None:
        """What to pass to the speech engine: None means detect automatically."""
        return None if self.language == "auto" else self.language

    def sessions_dir(self) -> Path:
        base = Path(self.save_dir) if self.save_dir else documents_dir() / "ILFU"
        return base / "sessions"


def config_path() -> Path:
    home = install_home()
    return (home if home else Path.home() / ".ilfu") / "config.json"


def default_save_dir() -> Path:
    return documents_dir() / "ILFU"


def load(path: Path | None = None) -> Config:
    path = path or config_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Config()
    known = {f.name for f in fields(Config)}
    return Config(**{k: v for k, v in raw.items() if k in known})


def save(cfg: Config, path: Path | None = None) -> None:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")


def needs_setup(cfg: Config) -> bool:
    return not cfg.setup_done or cfg.terms_version < TERMS_VERSION or not cfg.model
