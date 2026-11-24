"""Opt-in Chromium smoke test for the local simulator. Never opens Google."""

import os
import socket
import threading
import time
from urllib.request import urlopen

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright

from app.config import ROOT
from app.main import create_app


@pytest.mark.skipif(not os.getenv("FABRITAKE_TEST_CHROMIUM"), reason="Defina FABRITAKE_TEST_CHROMIUM=1 para o teste de interface.")
def test_simulated_workflow_in_chromium(tmp_path):
    assert (ROOT / "frontend/dist/index.html").is_file(), "Execute npm --prefix frontend run build."
    server = uvicorn.Server(uvicorn.Config(create_app(tmp_path), log_level="warning", access_log=False))
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        base = f"http://127.0.0.1:{listener.getsockname()[1]}"
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]})
        thread.start()
        try:
            for _ in range(60):
                if server.started:
                    break
                time.sleep(0.1)
            with urlopen(base + "/api/health", timeout=5) as response:
                assert response.status == 200
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=os.getenv("FABRITAKE_CHROMIUM_PATH") or None)
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base)
                expect(page.get_by_text("Conectado", exact=True)).to_be_visible()
                expect(page.get_by_role("heading", name="Visão geral")).to_be_visible()
                screenshot = os.getenv("FABRITAKE_TEST_SCREENSHOT")
                if screenshot:
                    page.screenshot(path=screenshot, full_page=True)
                page.get_by_role("button", name="Experimentar simulação").click()
                expect(page.get_by_role("heading", name="Monolito Modular")).to_be_visible()
                page.get_by_role("button", name="Iniciar geração").click()
                expect(page.get_by_text("3 de 3 cenas")).to_be_visible(timeout=20_000)
                page.get_by_role("button", name="02 Comunicação Concluído").click()
                expect(page.get_by_text("usa frame anterior", exact=False)).to_be_visible()
                assert page.locator("video").evaluate("(video) => video.canPlayType('video/mp4')") != ""
                page.locator("video").evaluate("(video) => video.play()")
                expect(page.get_by_alt_text("Frame final da cena")).to_be_visible()
                page.get_by_role("button", name="Arquivos").click()
                with page.expect_download() as download:
                    page.get_by_role("link", name="Baixar videos/02-comunicacao.mp4").click()
                assert download.value.suggested_filename == "02-comunicacao.mp4"
                page.set_viewport_size({"width": 390, "height": 850})
                page.get_by_role("link", name="Visão geral").click()
                expect(page.get_by_role("heading", name="Visão geral")).to_be_visible()
                overflow = page.evaluate("""() => ({
                    width: innerWidth, scroll: document.documentElement.scrollWidth,
                    elements: [...document.querySelectorAll('*')].filter(el => el.getBoundingClientRect().right > innerWidth)
                      .slice(0, 15).map(el => [el.tagName, el.className, Math.round(el.getBoundingClientRect().right)])
                })""")
                assert overflow["scroll"] == overflow["width"], overflow
                assert not errors
                browser.close()
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive()


@pytest.mark.skipif(not os.getenv("FABRITAKE_TEST_CHROMIUM"), reason="Defina FABRITAKE_TEST_CHROMIUM=1 para o teste de perfis.")
def test_persistent_profiles_are_isolated(tmp_path, monkeypatch):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from playwright.sync_api import BrowserType
    from app.infrastructure import providers

    class LocalPage(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"<h1>Local profile diagnostics</h1>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), LocalPage)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    monkeypatch.setattr(providers, "FLOW_URL", f"http://127.0.0.1:{server.server_port}")
    launch = BrowserType.launch_persistent_context

    def launch_headless(browser, directory, **options):
        return launch(browser, directory, **{**options, "headless": True})

    monkeypatch.setattr(BrowserType, "launch_persistent_context", launch_headless)
    manager = providers.BrowserInstanceManager(tmp_path)
    profile_a, profile_b = "a" * 32, "b" * 32

    def storage(identifier, script):
        def evaluate():
            context, _ = manager.sessions[identifier]
            return context.pages[0].evaluate(script)
        return manager.executor.submit(evaluate).result()

    try:
        assert manager.call("open", profile_a).availability == "manual"
        storage(profile_a, "() => localStorage.setItem('diagnostic', 'profile-a')")
        assert manager.call("close", profile_a).availability == "closed"
        assert manager.call("open", profile_b).availability == "manual"
        assert storage(profile_b, "() => localStorage.getItem('diagnostic')") is None
        assert manager.call("close", profile_b).availability == "closed"
        assert manager.call("open", profile_a).availability == "manual"
        assert storage(profile_a, "() => localStorage.getItem('diagnostic')") == "profile-a"
    finally:
        manager.shutdown()
        server.shutdown()
        server.server_close()
        thread.join()
