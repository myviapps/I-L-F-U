import pytest

from ilfu import config, models


class StubTranscriber:
    language = None
    beam_size = 1

    def transcribe(self, path):
        from ilfu.transcript import Segment

        return [Segment(0.0, 1.0, "hello from the stub")]


@pytest.fixture
def make_controller(tmp_path, monkeypatch):
    """A Controller with the fake audio backend, a stub model and files under tmp_path."""
    from ilfu.core import Controller

    monkeypatch.setattr(models, "models_root", lambda: tmp_path / "models")
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "cfg.json")
    monkeypatch.setattr(
        models, "_hub_fetch", lambda repo, target: (target / "model.bin").write_bytes(b"x")
    )

    def make(ready=True):
        cfg = config.Config(save_dir=str(tmp_path / "saved"))
        if ready:
            cfg.model, cfg.setup_done, cfg.terms_version = "base", True, config.TERMS_VERSION
            (tmp_path / "models" / "base").mkdir(parents=True, exist_ok=True)
            (tmp_path / "models" / "base" / models.COMPLETE_MARKER).write_text("x")
        c = Controller("fake", cfg, preload=False)
        c.transcriber = StubTranscriber() if ready else None
        c.model_state = "ready" if ready else "none"
        return c

    return make
