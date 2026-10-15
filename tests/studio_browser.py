"""Offline browser checks. Run with a Python environment that has Playwright.

No server, DNS, voice models or cloud credentials are needed: all routes are
fulfilled from fixtures. Screenshots go to --artifacts (default /tmp/voz-ui-qa).
"""
import argparse
import base64
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


CATALOG = {
    "ok": True,
    "catalogo": {
        "kokoro": {
            "etiqueta": "Kokoro (más natural, más lento)",
            "voces": {
                "fixture_dora": {"nombre": "Dora", "genero": "femenina", "idioma": "es"},
                "fixture_alex": {"nombre": "Alex", "genero": "masculina", "idioma": "es"},
            },
        },
        "piper": {
            "etiqueta": "Piper (más rápido, algo más plano)",
            "voces": {"fixture_mx": {"nombre": "Luz", "genero": "femenina", "idioma": "es-MX"}},
        },
        "empty": {"etiqueta": "No models", "voces": {}},
    },
}


def check_live(browser, url, artifacts):
    context = browser.new_context(viewport={"width": 1440, "height": 1080}, locale="es-ES", accept_downloads=True)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(url)
    page.wait_for_load_state("networkidle")
    expect(page.locator("#service-label")).to_have_text("Voces disponibles")
    page.locator("#script").fill("Un nuevo día comienza. Respira con calma y escucha tu voz.")
    page.locator("#engine").select_option("piper")
    page.locator("#voice").select_option("es_ES-davefx-medium")
    with page.expect_response("**/api/generar", timeout=180000) as response_info:
        page.locator("#generate").click()
    response = response_info.value
    assert response.ok, response.text()
    payload = response.json()
    expect(page.locator("#result")).to_be_visible()
    expect(page.locator("#progress")).to_be_hidden()
    page.wait_for_function("document.getElementById('result-audio').readyState >= 1")
    measured = page.locator("#result-audio").evaluate("audio => audio.duration")
    assert measured > 1, measured
    assert abs(measured - payload["duracion_s"]) < 1, (measured, payload)
    page.locator("#result-audio").evaluate("audio => audio.play()")
    page.wait_for_function("document.getElementById('result-audio').currentTime > 0.1")
    page.locator("#result-audio").evaluate("audio => audio.pause()")
    with page.expect_download() as download_info:
        page.locator("#download").click()
    downloaded = artifacts / download_info.value.suggested_filename
    download_info.value.save_as(downloaded)
    assert downloaded.stat().st_size > 1000
    page.screenshot(path=str(artifacts / "live-desktop.png"), full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    page.screenshot(path=str(artifacts / "live-mobile.png"), full_page=True)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert not errors, errors
    (artifacts / "live-result.json").write_text(json.dumps(payload, indent=2))
    print(json.dumps({"ok": True, "live": url, "metadata": payload, "browser_duration": measured, "download": str(downloaded)}))
    context.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", default="/tmp/voz-ui-qa")
    parser.add_argument("--live-url", help="Optional real studio origin; creates one short Piper MP3")
    args = parser.parse_args()
    artifacts = Path(args.artifacts)
    artifacts.mkdir(parents=True, exist_ok=True)
    html = (Path(__file__).resolve().parents[1] / "app/index.html").read_text()
    # A tiny PCM WAV fixture; media playback does not hit the network.
    audio_bytes = base64.b64decode("UklGRiYAAABXQVZFZm10IBAAAAABAAEAwF0AAIC7AAACABAAZGF0YQIAAAAAAA==")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            if args.live_url:
                check_live(browser, args.live_url, artifacts)
                return
            context = browser.new_context(viewport={"width": 1440, "height": 1080}, locale="es-ES")
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            state = {"catalog_status": 200, "history_status": 200, "files": [], "posts": [], "pending": []}

            def route_request(route):
                path = route.request.url.split("voice.test", 1)[1]
                if path == "/":
                    route.fulfill(content_type="text/html", body=html)
                elif path == "/api/voces":
                    route.fulfill(status=state["catalog_status"], json=CATALOG)
                elif path == "/api/historial":
                    route.fulfill(status=state["history_status"], json={"ok": True, "archivos": state["files"]})
                elif path == "/api/generar":
                    state["posts"].append(route.request.post_data_json)
                    state["pending"].append(route)
                elif path.startswith("/api/audio/"):
                    route.fulfill(content_type="audio/wav", body=audio_bytes)
                else:
                    raise AssertionError(f"Unexpected request: {route.request.url}")

            context.route("**/*", route_request)
            page.goto("http://voice.test/")
            page.wait_for_load_state("networkidle")
            expect(page.locator("html")).to_have_attribute("lang", "es")
            expect(page.locator("#service-label")).to_have_text("Voces disponibles")
            expect(page.locator("#generate")).to_be_disabled()
            expect(page.locator("#engine option[value=empty]")).to_be_disabled()
            expect(page.locator("#history-status")).to_contain_text("Tus audios aparecerán")
            expect(page.locator("#script")).to_have_attribute("maxlength", "40000")
            page.screenshot(path=str(artifacts / "desktop-empty.png"), full_page=True)

            script = "Overview <script>alert('fixture')</script>\n\nUn nuevo día comienza."
            page.locator("#script").fill("   ")
            expect(page.locator("#generate")).to_be_disabled()
            page.locator("#script").fill(script)
            expect(page.locator("#generate")).to_be_enabled()
            page.locator("#language-select").select_option("en")
            expect(page.locator("html")).to_have_attribute("lang", "en")
            expect(page.locator("#script")).to_have_value(script)
            expect(page.locator("#generate")).to_have_text("Generate voice")
            expect(page.locator("#engine option[value=kokoro]")).to_have_text("Kokoro")
            expect(page.locator("#engine-hint")).to_have_text("Kokoro (more natural, slower)")
            assert page.evaluate("localStorage.getItem('agenttube_language')") == "en"
            page.locator("#engine").select_option("piper")
            expect(page.locator("#voice")).to_have_value("fixture_mx")
            page.locator("#speed").focus()
            for _ in range(18):
                page.locator("#speed").press("ArrowRight")
            expect(page.locator("#speed-value")).to_have_text("1.1×")
            page.locator("#format").select_option("wav")
            page.locator("#generate").click()
            expect(page.locator("#progress")).to_be_visible()
            expect(page.locator("#generate")).to_be_disabled()
            expect(page.locator("#script")).to_have_attribute("readonly", "")
            page.wait_for_function("document.getElementById('elapsed').textContent !== '0:00'")
            page.evaluate("document.getElementById('voice-form').dispatchEvent(new Event('submit', {cancelable:true}))")
            assert len(state["posts"]) == 1
            assert state["posts"][0] == {"texto": script, "motor": "piper", "voz": "fixture_mx", "velocidad": 1.1, "formato": "wav"}
            page.locator("#language-select").select_option("es")
            expect(page.locator("#generate")).to_have_text("Generando…")
            page.screenshot(path=str(artifacts / "desktop-generating.png"), full_page=True)

            state["files"] = [{"archivo": "voz_123.wav", "url": "/api/audio/voz_123.wav", "cuando": 1790000000, "kb": 24}]
            result = {"ok": True, "url": "/api/audio/voz_123.wav", "motor": "piper", "voz": "fixture_mx", "velocidad": 1.1, "formato": "wav", "duracion_s": 12.4, "caracteres": len(script), "segundos_de_proceso": 1.3}
            state["pending"].pop(0).fulfill(json=result)
            expect(page.locator("#result")).to_be_visible()
            expect(page.locator("#progress")).to_be_hidden()
            expect(page.locator("#download")).to_have_attribute("href", "/api/audio/voz_123.wav")
            expect(page.locator("#metadata")).to_contain_text("0:12")
            expect(page.locator("#metadata")).to_contain_text("1,3 s")
            expect(page.locator(".history-item")).to_have_count(1)
            expect(page.locator("#generate")).to_be_enabled()
            page.screenshot(path=str(artifacts / "desktop-result.png"), full_page=True)
            for width in [320, 375, 390, 768, 1440]:
                page.set_viewport_size({"width": width, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), f"Overflow at {width}px"
                page.screenshot(path=str(artifacts / f"result-{width}.png"), full_page=True)

            # Server failures retain the script and previous valid result.
            page.locator("#generate").click()
            expect(page.locator("#progress")).to_be_visible()
            state["pending"].pop(0).fulfill(status=500, json={"detail": "fixture failure"})
            expect(page.locator("#error-box")).to_be_visible()
            expect(page.locator("#error-message")).to_contain_text("No se pudo generar")
            expect(page.locator("#script")).to_have_value(script)
            expect(page.locator("#generate")).to_be_enabled()
            expect(page.locator("#result")).to_be_visible()

            # Uncertain network failures direct users to the history before retry.
            page.locator("#generate").click()
            expect(page.locator("#progress")).to_be_visible()
            state["pending"].pop(0).abort("failed")
            expect(page.locator("#error-message")).to_contain_text("Revisa Audios recientes")

            page.locator("#generate").click()
            expect(page.locator("#progress")).to_be_visible()
            state["pending"].pop(0).fulfill(status=401, json={"detail": "expired"})
            expect(page.locator("#sign-in")).to_be_visible()
            expect(page.locator("#error-message")).to_contain_text("sesión ha caducado")

            # A malicious audio URL must never become a player/download target.
            page.locator("#generate").click()
            expect(page.locator("#progress")).to_be_visible()
            state["pending"].pop(0).fulfill(json={**result, "url": "https://outside.example/evil.mp3"})
            expect(page.locator("#error-message")).to_contain_text("respuesta no válida")
            expect(page.locator("#download")).to_have_attribute("href", "/api/audio/voz_123.wav")

            # Translation never interprets user-supplied filenames as HTML.
            state["files"][0]["archivo"] = '<img src=x onerror="window.injected=true">.wav'
            page.locator("#refresh").click()
            expect(page.locator(".file-name")).to_have_text(state["files"][0]["archivo"])
            expect(page.locator("#history-list img")).to_have_count(0)
            page.locator("#language-select").select_option("en")
            expect(page.locator(".file-name")).to_have_text(state["files"][0]["archivo"])
            page.reload()
            expect(page.locator("html")).to_have_attribute("lang", "en")

            # Catalog failure/retry; history failure/retry with existing audio kept.
            state["catalog_status"] = 503
            page.reload()
            expect(page.locator("#retry-catalog")).to_be_visible()
            expect(page.locator("#engine")).to_be_disabled()
            state["catalog_status"] = 200
            page.locator("#retry-catalog").click()
            expect(page.locator("#engine")).to_be_enabled()
            state["history_status"] = 500
            page.locator("#refresh").click()
            expect(page.locator("#history-status")).to_contain_text("Could not load")
            expect(page.locator(".history-item")).to_have_count(1)
            state["history_status"] = 200
            page.locator("#refresh").click()
            expect(page.locator("#history-status")).to_be_hidden()

            # Language still works when localStorage is blocked.
            context.add_init_script("Object.defineProperty(window, 'localStorage', { get() { throw new Error('blocked'); } });")
            page.reload()
            page.locator("#language-select").select_option("en")
            expect(page.locator("html")).to_have_attribute("lang", "en")
            assert not errors, errors
            print(json.dumps({"ok": True, "checks": ["catalog", "voice switching", "ES/EN", "script preservation", "loading and duplicate submission", "generation", "metadata", "history", "320-1440px overflow", "server/network/auth failures", "untrusted responses", "retry", "blocked storage"], "artifacts": str(artifacts)}))
        finally:
            browser.close()


if __name__ == "__main__":
    main()
