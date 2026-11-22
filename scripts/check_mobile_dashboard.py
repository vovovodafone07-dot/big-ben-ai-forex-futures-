"""Run a touch layout and chart smoke test with local, deterministic data."""
import argparse
from datetime import datetime, timedelta, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect, sync_playwright


PLATFORM = Path(__file__).resolve().parents[1] / "platform"
SYMBOLS = ("OANDA:EURUSD", "OANDA:GBPUSD")


class SiteHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


def candle_history():
    start = datetime(2026, 11, 20, 0, 0, tzinfo=timezone.utc)
    return [
        {
            "time": (start + timedelta(minutes=5 * index)).isoformat(),
            "open": 1.10 + index * 0.00001,
            "high": 1.101 + index * 0.00001,
            "low": 1.099 + index * 0.00001,
            "close": 1.1005 + index * 0.00001,
        }
        for index in range(400)
    ]


def install_fixtures(page, origin):
    candles = candle_history()
    symbols = [
        {"symbol": symbol, "label": symbol, "asset_class": "forex", "connected": True,
         "fresh": True, "market_state": "شموع حديثة"}
        for symbol in SYMBOLS
    ]
    fixtures = {
        "/api/events": {"events": [{"symbol": SYMBOLS[0], "event_id": "mobile-fixture",
                                     "event": "BUY", "time": candles[-1]["time"],
                                     "entry": 1.105, "sl": 1.101, "tp": 1.117}]},
        "/api/analysis": {"symbols": []},
        "/api/status": {"symbols": []},
        "/api/trade-journal": {"records": []},
        "/api/tracked-symbols": {"symbols": symbols},
        "/api/agent": {"services": {"storage": "fixture"}, "research": {"signals_examined": 0},
                       "pattern_audits": [], "tracked_symbols": []},
        "/api/news": {"sources": [], "news": [], "calendar": []},
    }

    def respond(route):
        url = urlsplit(route.request.url)
        if not route.request.url.startswith(origin + "/"):
            route.abort()
        elif url.path.startswith(("/api/", "/healthz")):
            if url.path == "/api/chart/candles":
                symbol = parse_qs(url.query).get("symbol", [SYMBOLS[0]])[0]
                route.fulfill(json={"symbol": symbol, "provider": "بيانات اختبار",
                                    "candles": candles, "fresh": True,
                                    "last_closed_candle": candles[-1]["time"]})
            elif url.path in fixtures:
                route.fulfill(json=fixtures[url.path])
            else:
                route.fulfill(status=503, json={"error": "fixture_unavailable"})
        else:
            route.continue_()

    page.route("**/*", respond)


def require_fit(page):
    overflowing = page.evaluate("""() => {
        if (document.documentElement.scrollWidth <= innerWidth + 1) return [];
        return [...document.querySelectorAll('body *')].filter(el => {
            const box = el.getBoundingClientRect();
            return box.width && !el.closest('[hidden]') && (box.left < -1 || box.right > innerWidth + 1);
        }).slice(0, 12).map(el => [el.id || el.className, el.getBoundingClientRect().width]);
    }""")
    assert not overflowing, f"Page overflow on {page.url}: {overflowing}"


def check_dashboard(browser, origin, width, height):
    page = browser.new_page(viewport={"width": width, "height": height},
                            is_mobile=True, has_touch=True, device_scale_factor=2)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    install_fixtures(page, origin)
    page.goto(origin + "/#analyze", wait_until="domcontentloaded")
    picker = page.locator("#desk-symbol")
    expect(picker.locator("option")).to_have_count(2)
    picker.select_option(SYMBOLS[1])
    expect(page.locator("#desk-chart-status")).to_contain_text(SYMBOLS[1])
    expect(page.locator("#desk-chart-status")).to_contain_text("400")
    require_fit(page)

    canvas = page.locator("#bigben-native-candles")
    page.wait_for_function("""() => {
      const canvas = document.getElementById('bigben-native-candles');
      return Math.abs(canvas.width - canvas.clientWidth * 2) <= 2
        && canvas.getContext('2d').getImageData(1,1,1,1).data[0] === 255;
    }""")
    expect(page.locator(".ref-trade-levels")).to_be_visible()
    for selector in ("#desk-symbol", "[data-chart-timeframe=M15]", "[data-zoom=in]", "#ref-chart-expand"):
        assert page.locator(selector).bounding_box()["height"] >= 44, selector

    m15 = page.locator("[data-chart-timeframe=M15]")
    m15.tap()
    expect(m15).to_have_attribute("aria-pressed", "true")
    expect(page.locator("#ref-chart-timeframe")).to_have_text("M15")
    before = canvas.evaluate("(canvas) => canvas.toDataURL()")
    page.locator("[data-zoom=in]").tap()
    page.wait_for_function("before => document.querySelector('canvas').toDataURL() !== before", arg=before)
    page.locator("[data-chart-timeframe=M5]").tap()

    expand = page.locator("#ref-chart-expand")
    close = page.locator("#ref-chart-close")
    expand.tap()
    expect(expand).to_have_attribute("aria-expanded", "true")
    expect(close).to_be_visible()
    assert close.bounding_box()["height"] >= 44
    require_fit(page)
    close.tap()
    expect(expand).to_have_attribute("aria-expanded", "false")
    expect(close).to_be_hidden()
    expand.tap()
    page.keyboard.press("Escape")
    expect(close).to_be_hidden()

    for section in ("signals", "agents", "news", "settings"):
        nav = page.locator(f'.sidebar button[data-target="{section}"]')
        nav.tap()
        expect(nav).to_have_class("active")
        require_fit(page)
        if section == "signals":
            for field in ("entry", "sl", "tp", "rr"):
                expect(page.locator(f"#ov-{field}")).not_to_have_text("—")
            assert page.locator(".overview-focus").bounding_box()["y"] < page.locator("#overview.kpi").bounding_box()["y"]
    page.locator(".ref-more>summary").tap()
    expect(page.locator('.ref-more button[data-target="trade-setup"]')).to_be_visible()
    require_fit(page)
    assert not errors, errors
    print(f"PASS {browser.browser_type.name}: {width}×{height}")
    page.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("engine", choices=("chromium", "webkit"))
    parser.add_argument("--executable")
    args = parser.parse_args()
    handler = partial(SiteHandler, directory=str(PLATFORM))
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server, sync_playwright() as playwright:
        Thread(target=server.serve_forever, daemon=True).start()
        browser_type = getattr(playwright, args.engine)
        browser = browser_type.launch(executable_path=args.executable)
        try:
            origin = f"http://127.0.0.1:{server.server_port}"
            for width, height in ((320, 667), (390, 844), (430, 932)):
                check_dashboard(browser, origin, width, height)
        finally:
            browser.close()
            server.shutdown()


if __name__ == "__main__":
    main()
