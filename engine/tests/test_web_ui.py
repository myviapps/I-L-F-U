"""Drives the real page in a real browser. Skipped when Playwright or Chromium is missing."""

import glob
import os
import threading

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

from ilfu import models  # noqa: E402
from ilfu.server import IlfuServer  # noqa: E402


def _chromium():
    explicit = os.environ.get("ILFU_CHROMIUM")
    if explicit:
        return explicit
    for pattern in ("/opt/pw-browsers/chromium-*/chrome-linux/chrome",):
        found = glob.glob(pattern)
        if found:
            return found[0]
    return None


@pytest.fixture
def page(request):
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch(executable_path=_chromium(), args=["--no-sandbox"])
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"no Chromium available: {exc}")
        pg = browser.new_page(viewport={"width": 1200, "height": 800})
        pg.errors = []
        pg.on("pageerror", lambda e: pg.errors.append(str(e)))
        pg.on("console", lambda m: m.type == "error" and pg.errors.append(m.text))
        yield pg
        browser.close()


def _serve(controller):
    srv = IlfuServer(controller)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_record_stop_rename_delete_in_the_browser(page, make_controller):
    c = make_controller()
    srv = _serve(c)
    try:
        page.goto(srv.url)
        page.wait_for_selector("#rec")
        page.click("#rec")
        page.click("#yes")  # consent dialog
        page.wait_for_selector("#livebox")
        c.live._chunk_seconds = 0.5
        page.wait_for_selector("#livebox .line", timeout=15000)
        assert "hello from the stub" in page.inner_text("#livebox")
        page.click("#lpause")
        page.wait_for_selector("#lstate:has-text('Paused')")
        page.click("#lpause")
        page.click("#lstop")
        page.wait_for_selector("#tbox .line", timeout=20000)  # the saved recording opens
        assert page.locator("#audio").count() == 1
        page.fill("#tsearch", "stub")
        assert page.locator("#tbox mark").count() >= 1
        page.click("#editTitle")
        page.fill("#ti", "Quarterly review")
        page.press("#ti", "Enter")
        page.wait_for_selector("#titleText:has-text('Quarterly review')")
        assert "Quarterly review" in page.inner_text("#list")
        page.click("#del")
        page.click("#yes")
        page.wait_for_selector("#rec")
        page.wait_for_function("document.querySelector('#list').innerText.includes('No recordings')")
        assert not page.errors, page.errors
    finally:
        srv.shutdown()
        srv.server_close()


def test_first_run_wizard_in_the_browser(page, make_controller, monkeypatch):
    c = make_controller(ready=False)
    monkeypatch.setattr(c, "load_model", lambda: None)
    srv = _serve(c)
    try:
        page.goto(srv.url)
        page.wait_for_selector("#acc")
        assert page.is_disabled("#next")  # cannot continue without accepting
        page.check("#acc")
        page.click("#next")
        page.wait_for_selector("#dir")
        page.fill("#dir", str(c.cfg.sessions_dir().parent))
        page.click("#next")
        page.wait_for_selector("#lang")
        page.select_option("#lang", "te")
        page.check("input[value=base]")
        page.click("#next")  # download and finish
        page.wait_for_selector("#rec", timeout=20000)
        assert c.cfg.language == "te" and c.cfg.model == "base"
        assert models.is_downloaded("base")
        assert not page.errors, page.errors
    finally:
        srv.shutdown()
        srv.server_close()


def test_settings_page_and_dark_mode_render(page, make_controller):
    c = make_controller()
    srv = _serve(c)
    try:
        page.emulate_media(color_scheme="dark")
        page.goto(srv.url)
        page.click("#settingsBtn")
        page.wait_for_selector("#sApply")
        assert page.locator("input[name=model]").count() == 4
        assert not page.errors, page.errors
    finally:
        srv.shutdown()
        srv.server_close()


def test_device_pickers_and_audio_test(page, make_controller):
    c = make_controller()
    srv = _serve(c)
    try:
        page.goto(srv.url)
        page.click("#testAudio")
        page.wait_for_selector("text=Audio test", timeout=15000)
        assert page.locator("text=Working").count() == 2  # fake microphone and call sound
        page.click("#ok")
        page.click("#settingsBtn")
        page.wait_for_selector("#sMic option:has-text('Fake headset microphone')", state="attached")
        page.select_option("#sMic", "Fake headset microphone")
        page.select_option("#sSpk", "Fake headset")
        page.click("#sApply")
        page.wait_for_function("true")
        for _ in range(50):
            if c.cfg.mic_device:
                break
            page.wait_for_timeout(100)
        assert c.cfg.mic_device == "Fake headset microphone" and c.cfg.speaker_device == "Fake headset"
        assert not page.errors, page.errors
    finally:
        srv.shutdown()
        srv.server_close()
