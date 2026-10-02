import wave

import pytest

tk = pytest.importorskip("tkinter")


def _root():
    try:
        return tk.Tk()
    except tk.TclError:
        pytest.skip("no display available")


class Stub:
    language = None
    beam_size = 1

    def transcribe(self, path):
        from ilfu.transcript import Segment

        return [Segment(0.0, 1.0, "hello from the stub")]


def _pump(root, seconds):
    import time

    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.05)


def test_window_builds_and_closes(tmp_path):
    from ilfu import config
    from ilfu.gui import App

    root = _root()
    app = App(root, backend="fake", cfg=config.Config(save_dir=str(tmp_path)))
    root.update()
    assert "I-L-F-U" in root.title()
    assert app.recorder is None
    root.destroy()


def test_record_pause_stop_rename_delete(tmp_path, monkeypatch):
    from tkinter import messagebox, simpledialog

    from ilfu import config
    from ilfu.gui import App

    monkeypatch.setattr(messagebox, "askokcancel", lambda *a, **k: True)
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    monkeypatch.setattr(messagebox, "showerror", lambda *a, **k: pytest.fail(str(a)))
    monkeypatch.setattr(simpledialog, "askstring", lambda *a, **k: "Team sync")
    root = _root()
    cfg = config.Config(save_dir=str(tmp_path), model="base", setup_done=True)
    app = App(root, backend="fake", cfg=cfg)
    app.transcriber = Stub()
    app.start()
    assert app.recorder is not None
    _pump(root, 1.0)
    app.toggle_pause()
    assert app.paused
    app.toggle_pause()
    app.live._chunk_seconds = 0.5
    _pump(root, 2.0)
    assert "hello from the stub" in app.text.get("1.0", "end")  # live captions appeared
    app.stop()
    _pump(root, 2.0)
    assert not app.busy
    sessions = list(app.sessions.values())
    assert len(sessions) == 1
    assert (sessions[0].path / "transcript.md").exists()
    with wave.open(str(sessions[0].path / "mic.wav"), "rb") as wav:
        assert wav.getnframes() > 0
    app.tree.selection_set(str(sessions[0].path))
    app.rename()
    assert app.selected().title == "Team sync"
    app.delete()
    assert app.sessions == {}
    root.destroy()


def test_setup_wizard_walks_through_and_saves(tmp_path, monkeypatch):
    from ilfu import config, models
    from ilfu.wizard import SetupWizard

    monkeypatch.setattr(models, "models_root", lambda: tmp_path / "models")
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "cfg.json")
    monkeypatch.setattr(
        models, "_hub_fetch", lambda repo, target: (target / "model.bin").write_bytes(b"x")
    )
    root = _root()
    done = []
    wiz = SetupWizard(root, config.Config(), done.append)
    wiz.next()  # blocked: agreement not accepted
    assert wiz.step == 0
    wiz.agree.set(True)
    wiz.next()
    wiz.folder.set(str(tmp_path / "saved"))
    wiz.next()
    wiz.language.set(config.LANGUAGES["te"])
    wiz.model.set("base")
    wiz.next()
    assert wiz.step == 3
    _pump(root, 2.0)
    assert wiz.download_ok
    wiz.next()  # Finish
    root.update()
    assert done and done[0].language == "te" and done[0].model == "base"
    saved = config.load(tmp_path / "cfg.json")
    assert not config.needs_setup(saved)
    assert saved.save_dir == str(tmp_path / "saved")
    assert (tmp_path / "saved").is_dir()
    root.destroy()
