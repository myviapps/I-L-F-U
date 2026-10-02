"""CI only: run the real app (real speech model, fake audio source) and drive it over HTTP."""

import json
import sys
import threading
import time
import urllib.request

from ilfu import config
from ilfu.core import Controller
from ilfu.server import COOKIE, IlfuServer

cfg = config.load()
assert not config.needs_setup(cfg), "setup was not saved"
controller = Controller("fake", cfg)
server = IlfuServer(controller)
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{server.server_address[1]}"


def call(path, method="GET", raw=False):
    req = urllib.request.Request(base + path, method=method, data=b"{}" if method == "POST" else None)
    req.add_header("Cookie", f"{COOKIE}={server.token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
        return data if raw else json.loads(data)


def wait(cond, seconds, what):
    end = time.time() + seconds
    while time.time() < end:
        if cond():
            return
        time.sleep(0.3)
    raise SystemExit(f"timed out waiting for {what}: {call('/api/state')}")


page = urllib.request.Request(base + "/?t=" + server.token)
assert b"I-L-F-U" in urllib.request.urlopen(page, timeout=10).read(), "page did not load"
wait(lambda: call("/api/state")["model_state"] in ("ready", "error"), 240, "the speech model")
state = call("/api/state")
assert state["model_state"] == "ready", f"speech model failed: {state['model_error']}"
print("model loaded")

call("/api/record/start", "POST")
time.sleep(6)
call("/api/record/pause", "POST")
time.sleep(1)
call("/api/record/resume", "POST")
time.sleep(3)
call("/api/record/stop", "POST")
wait(lambda: not call("/api/state")["busy"], 120, "the recording to be saved")

sessions = call("/api/sessions")
assert len(sessions) == 1, sessions
sid = sessions[0]["id"]
audio = call(f"/audio/{sid}", raw=True)
assert audio[:4] == b"RIFF" and len(audio) > 10000, "audio not served"
print("recording saved and served:", sid, f"{sessions[0]['duration']}s", f"{len(audio)} bytes")
controller.shutdown()
server.shutdown()
sys.exit(0)
