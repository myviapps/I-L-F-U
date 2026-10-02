import json
import time
import urllib.error
import urllib.request

import pytest

from ilfu.server import COOKIE, IlfuServer


@pytest.fixture
def server(make_controller):
    import threading

    srv = IlfuServer(make_controller())
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()
    srv.server_close()


def call(srv, path, method="GET", body=None, cookie=True, host=None, headers=None):
    port = srv.server_address[1]
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
    )
    if cookie:
        req.add_header("Cookie", f"{COOKIE}={srv.token}")
    if host:
        req.add_header("Host", host)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read(), resp.headers
    except urllib.error.HTTPError as err:
        return err.code, err.read(), err.headers


def test_page_needs_the_token_and_sets_a_cookie(server):
    assert call(server, "/", cookie=False)[0] == 403
    status, body, headers = call(server, f"/?t={server.token}", cookie=False)
    assert status == 200 and b"I-L-F-U" in body
    assert COOKIE in headers["Set-Cookie"] and "SameSite=Strict" in headers["Set-Cookie"]


def test_api_rejects_missing_cookie_and_foreign_host(server):
    assert call(server, "/api/state", cookie=False)[0] == 403
    assert call(server, "/api/state", host="evil.example.com")[0] == 403
    assert call(server, "/api/state")[0] == 200


def test_state_and_catalog(server):
    state = json.loads(call(server, "/api/state")[1])
    assert state["setup_needed"] is False and state["model_state"] == "ready"
    cat = json.loads(call(server, "/api/catalog")[1])
    assert {m["name"] for m in cat["models"]} >= {"base", "small"}
    assert any(lang["code"] == "te" for lang in cat["languages"])


def test_full_flow_over_http(server):
    assert call(server, "/api/record/start", "POST")[0] == 200
    server.controller.live._chunk_seconds = 0.5
    time.sleep(2.0)
    assert call(server, "/api/record/pause", "POST")[0] == 200
    assert call(server, "/api/record/resume", "POST")[0] == 200
    time.sleep(1.0)
    assert call(server, "/api/record/stop", "POST")[0] == 200
    for _ in range(100):
        if not json.loads(call(server, "/api/state")[1])["busy"]:
            break
        time.sleep(0.1)
    sessions = json.loads(call(server, "/api/sessions")[1])
    assert len(sessions) == 1
    sid = sessions[0]["id"]
    detail = json.loads(call(server, f"/api/sessions/{sid}")[1])
    assert detail["segments"]
    # audio with a range request, as the browser player does
    status, data, headers = call(server, f"/audio/{sid}", headers={"Range": "bytes=0-99"})
    assert status == 206 and len(data) == 100 and headers["Content-Range"].startswith("bytes 0-99/")
    status, data, headers = call(server, f"/audio/{sid}")
    assert status == 200 and data[:4] == b"RIFF"
    status, text, headers = call(server, f"/api/sessions/{sid}/export?fmt=md")
    assert status == 200 and b"hello from the stub" in text and "attachment" in headers["Content-Disposition"]
    assert call(server, f"/api/sessions/{sid}/rename", "POST", {"title": "Standup"})[0] == 200
    assert json.loads(call(server, f"/api/sessions/{sid}")[1])["title"] == "Standup"
    assert call(server, f"/api/sessions/{sid}", "DELETE")[0] == 200
    assert call(server, f"/api/sessions/{sid}")[0] == 404


def test_errors_are_plain_json(server):
    status, body, _ = call(server, "/api/record/stop", "POST")
    assert status == 400 and "error" in json.loads(body)
    assert call(server, "/api/nothing")[0] == 404
    status, body, _ = call(server, "/api/sessions/..%2f..%2fetc")
    assert status in (400, 404)


def test_watchdog_exits_after_the_window_closes(make_controller, monkeypatch):
    import threading

    from ilfu import server as server_module

    monkeypatch.setattr(server_module, "BYE_GRACE_SECONDS", 0.2)
    srv = IlfuServer(make_controller())
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    threading.Thread(target=srv.watchdog, daemon=True).start()
    call(srv, "/api/bye", "POST")
    t.join(timeout=6)
    assert not t.is_alive()
    srv.server_close()


def test_watchdog_keeps_running_while_recording(make_controller, monkeypatch):
    import threading

    from ilfu import server as server_module

    monkeypatch.setattr(server_module, "BYE_GRACE_SECONDS", 0.2)
    srv = IlfuServer(make_controller())
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    threading.Thread(target=srv.watchdog, daemon=True).start()
    call(srv, "/api/record/start", "POST")
    call(srv, "/api/bye", "POST")
    time.sleep(2.5)
    assert t.is_alive()  # a recording is never cut off by closing the window
    srv.controller.stop_recording()
    t.join(timeout=8)
    assert not t.is_alive()
    srv.server_close()
