import time
import wave

import pytest

from ilfu.core import ApiError


def wait(cond, seconds=10):
    end = time.time() + seconds
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_setup_flow_downloads_then_marks_ready(make_controller):
    c = make_controller(ready=False)
    assert c.state()["setup_needed"]
    with pytest.raises(ApiError):
        c.setup(False, "", "auto", "base")  # agreement required
    with pytest.raises(ApiError):
        c.setup(True, "", "xx", "base")
    with pytest.raises(ApiError):
        c.setup(True, "", "auto", "nope")
    c.setup(True, str(c.cfg.sessions_dir().parent), "te", "base")
    assert wait(lambda: c.download["state"] == "done")
    assert wait(lambda: not c.state()["setup_needed"])
    assert c.cfg.language == "te" and c.cfg.model == "base" and c.cfg.setup_done


def test_cannot_record_before_setup(make_controller):
    c = make_controller(ready=False)
    with pytest.raises(ApiError):
        c.start_recording()


def test_record_pause_stop_history_rename_delete(make_controller):
    c = make_controller()
    c.start_recording()
    with pytest.raises(ApiError):
        c.start_recording()
    c.live._chunk_seconds = 0.5
    time.sleep(1.5)
    c.pause()
    assert c.state()["paused"]
    paused_at = c.elapsed()
    time.sleep(0.3)
    assert abs(c.elapsed() - paused_at) < 0.05  # the clock stops while paused
    c.resume()
    time.sleep(1.5)
    assert wait(lambda: c.segments), "no live captions"
    c.stop_recording()
    assert wait(lambda: not c.busy)
    sessions = c.sessions()
    assert len(sessions) == 1
    sid = sessions[0]["id"]
    assert c.last_finished == sid
    detail = c.session(sid)
    assert detail["segments"] and detail["playable"]
    assert {s["speaker"] for s in detail["segments"]} <= {"You", "Them"}
    with wave.open(str(c.audio_file(sid)), "rb") as wav:
        assert wav.getnframes() > 0
    text, name = c.export(sid, "srt")
    assert "hello from the stub" in text and name.endswith(".srt")
    c.rename(sid, "  Team sync  ")
    assert c.session(sid)["title"] == "Team sync"
    with pytest.raises(ApiError):
        c.rename(sid, "   ")
    c.delete(sid)
    assert c.sessions() == []


def test_retranscribe_replaces_transcript(make_controller):
    c = make_controller()
    c.start_recording()
    time.sleep(1.2)
    c.stop_recording()
    assert wait(lambda: not c.busy)
    sid = c.sessions()[0]["id"]
    c.retranscribe(sid)
    assert wait(lambda: not c.busy)
    assert c.transcriber.beam_size == 1  # restored after the accurate pass
    assert c.session(sid)["segments"]


@pytest.mark.parametrize("bad", ["../x", "..", "a/b", "a\\b", "missing"])
def test_session_ids_cannot_escape_the_folder(make_controller, bad):
    c = make_controller()
    with pytest.raises(ApiError):
        c.session(bad)
    with pytest.raises(ApiError):
        c.delete(bad)


def test_language_can_change_while_ready(make_controller):
    c = make_controller()
    c.set_language("hi")
    assert c.transcriber.language == "hi" and c.cfg.language == "hi"
    with pytest.raises(ApiError):
        c.set_language("klingon")
