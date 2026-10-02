"""A small local web server: the app's interface runs in the browser engine on this computer.

It listens on 127.0.0.1 only, checks the Host header (blocks DNS rebinding) and requires a random
token cookie (blocks other websites from talking to it). Nothing leaves this computer.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import re
import secrets
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from .core import ApiError, Controller

log = logging.getLogger("ilfu")
COOKIE = "ilfu_token"
IDLE_EXIT_SECONDS = 600  # nobody has talked to the server for this long
BYE_GRACE_SECONDS = 10  # the window was closed; wait in case it was only a refresh


class IlfuServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, controller: Controller, port: int = 0) -> None:
        super().__init__(("127.0.0.1", port), Handler)
        self.controller = controller
        self.token = secrets.token_urlsafe(24)
        self.last_seen = time.time()
        self.bye_at: float | None = None
        self.stop_event = threading.Event()
        self.quit_requested = False

    def handle_error(self, request: object, client_address: object) -> None:
        # Browsers drop connections all the time (page closed, audio seek); that is not an error.
        import sys

        if isinstance(sys.exc_info()[1], (ConnectionError, TimeoutError)):
            return
        log.exception("server error")

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}/?t={self.token}"

    def busy(self) -> bool:
        c = self.controller
        return c.recorder is not None or bool(c.busy) or c.download["state"] == "running"

    def watchdog(self) -> None:
        """Exit when the window is gone, unless a recording or a download is still running."""
        while not self.stop_event.wait(1.0):
            if self.busy():
                continue
            now = time.time()
            gone = self.bye_at is not None and now - self.bye_at > BYE_GRACE_SECONDS
            idle = now - self.last_seen > IDLE_EXIT_SECONDS
            if gone or idle or self.quit_requested:
                log.info("closing: window gone=%s idle=%s", gone, idle)
                self.shutdown()
                return


class Handler(BaseHTTPRequestHandler):
    server: IlfuServer
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: object) -> None:  # keep the console quiet
        log.debug(fmt, *args)

    # ---- plumbing ----
    def _send(self, status: int, body: bytes, ctype: str, headers: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, data: object, status: int = 200) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode(), "application/json")

    def _fail(self, message: str, status: int = 400) -> None:
        self._json({"error": message}, status)

    def _host_ok(self) -> bool:
        port = self.server.server_address[1]
        return self.headers.get("Host", "") in (f"127.0.0.1:{port}", f"localhost:{port}")

    def _cookie_ok(self) -> bool:
        for part in self.headers.get("Cookie", "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == COOKIE and secrets.compare_digest(value, self.server.token):
                return True
        return False

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > 1_000_000:
            raise ApiError("Request too large.", 413)
        raw = self.rfile.read(length) if length else b""
        try:
            return json.loads(raw or b"{}")
        except ValueError as exc:
            raise ApiError("Bad request.") from exc

    def _dispatch(self) -> None:
        if not self._host_ok():
            return self._fail("Forbidden", 403)
        url = urlparse(self.path)
        query = parse_qs(url.query)
        self.server.last_seen = time.time()
        if url.path == "/" and self.command in ("GET", "HEAD"):
            token = (query.get("t") or [""])[0]
            if not (secrets.compare_digest(token, self.server.token) or self._cookie_ok()):
                return self._fail("Open the app from its Start Menu shortcut.", 403)
            self.server.bye_at = None
            page = resources.files("ilfu").joinpath("web/index.html").read_bytes()
            cookie = f"{COOKIE}={self.server.token}; Path=/; HttpOnly; SameSite=Strict"
            return self._send(200, page, "text/html; charset=utf-8", {"Set-Cookie": cookie})
        if not self._cookie_ok():
            return self._fail("Not allowed", 403)
        try:
            self._route(url.path, query)
        except ApiError as exc:
            self._fail(str(exc), exc.status)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            log.exception("request failed: %s %s", self.command, self.path)
            self._fail(f"Something went wrong: {exc}", 500)

    do_GET = do_POST = do_DELETE = do_HEAD = _dispatch

    # ---- routes ----
    def _route(self, path: str, query: dict) -> None:
        c = self.server.controller
        method = self.command
        if path == "/api/state" and method == "GET":
            since = int((query.get("since") or ["0"])[0])
            self.server.bye_at = None
            return self._json(c.state(since))
        if path == "/api/catalog":
            return self._json(c.catalog())
        if path == "/api/bye" and method == "POST":
            self.server.bye_at = time.time()
            return self._json({"ok": True})
        if path == "/api/quit" and method == "POST":
            c.shutdown()
            self.server.quit_requested = True
            return self._json({"ok": True})
        if path == "/api/setup" and method == "POST":
            b = self._body()
            c.setup(bool(b.get("accept_terms")), str(b.get("save_dir", "")),
                    str(b.get("language", "auto")), str(b.get("model", "")))
            return self._json(c.state())
        if path == "/api/pick-folder" and method == "POST":
            return self._json({"path": pick_folder()})
        if path == "/api/record/start" and method == "POST":
            c.start_recording()
            return self._json(c.state())
        if path == "/api/record/pause" and method == "POST":
            c.pause()
            return self._json(c.state())
        if path == "/api/record/resume" and method == "POST":
            c.resume()
            return self._json(c.state())
        if path == "/api/record/stop" and method == "POST":
            c.stop_recording()
            return self._json(c.state())
        if path == "/api/error/clear" and method == "POST":
            c.clear_error()
            return self._json({"ok": True})
        if path == "/api/language" and method == "POST":
            c.set_language(str(self._body().get("language", "auto")))
            return self._json(c.state())
        if path == "/api/uninstall" and method == "POST":
            from .uninstall import launch_uninstaller

            message = launch_uninstaller()
            started = message.startswith("The uninstaller has started")
            if started:
                c.shutdown()
                self.server.quit_requested = True
            return self._json({"message": message, "started": started})
        if path == "/api/sessions" and method == "GET":
            return self._json(c.sessions())
        m = re.fullmatch(r"/api/sessions/([^/]+)(?:/(rename|retranscribe|export))?", path)
        if m:
            sid, action = unquote(m[1]), m[2]
            if action is None and method == "GET":
                return self._json(c.session(sid))
            if action is None and method == "DELETE":
                c.delete(sid)
                return self._json({"ok": True})
            if action == "rename" and method == "POST":
                c.rename(sid, str(self._body().get("title", "")))
                return self._json({"ok": True})
            if action == "retranscribe" and method == "POST":
                c.retranscribe(sid)
                return self._json(c.state())
            if action == "export" and method == "GET":
                text, name = c.export(sid, (query.get("fmt") or ["md"])[0])
                disposition = f"attachment; filename*=UTF-8''{quote(name)}"
                return self._send(200, text.encode(), "text/plain; charset=utf-8",
                                  {"Content-Disposition": disposition})
        m = re.fullmatch(r"/audio/([^/]+)", path)
        if m and method in ("GET", "HEAD"):
            return self._serve_audio(c.audio_file(unquote(m[1])))
        raise ApiError("Not found.", 404)

    def _serve_audio(self, path: Path) -> None:
        """Serve a WAV with Range support so the player can seek."""
        size = path.stat().st_size
        start, end, status = 0, size - 1, 200
        header = self.headers.get("Range", "")
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", header)
        if m and (m[1] or m[2]):
            if m[1]:
                start = int(m[1])
                end = int(m[2]) if m[2] else size - 1
            else:
                start = max(0, size - int(m[2]))
            end = min(end, size - 1)
            if start > end:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            status = 206
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "audio/wav")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if self.command == "HEAD":
            return
        with path.open("rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining > 0:
                chunk = handle.read(min(65536, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)


def pick_folder() -> str:
    """Ask Windows for a folder with its normal dialog. Empty string if cancelled or unavailable."""
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        chosen = filedialog.askdirectory(parent=root)
        root.destroy()
        return str(Path(chosen)) if chosen else ""
    except Exception:  # noqa: BLE001 - the page falls back to typing the path
        return ""
