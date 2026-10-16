"""Refresh app/data/maps_pb.txt and the test fixture from a real Google Maps session.

Only needed if Google changes its format and searches start returning nothing.
Opens Microsoft Edge (headless), runs one search, and saves the request
template and a trimmed response.

    pip install playwright
    python tools/capture_maps_template.py
"""
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.core.scraper import decode  # noqa: E402

QUERY = "restaurants in Lahore"


def main() -> None:
    captured = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(locale="en-US")

        def on_response(response):
            if "tbm=map" in response.url and "!1s" in response.url and "url" not in captured:
                captured["url"], captured["body"] = response.url, response.text()

        page.on("response", on_response)
        page.goto("https://www.google.com/maps/search/" + QUERY.replace(" ", "+") + "?hl=en")
        page.wait_for_timeout(8000)
        browser.close()
    if "url" not in captured:
        sys.exit("No search request seen. Is there a cookie consent page? Try with headless=False.")

    pb = parse_qs(urlsplit(captured["url"]).query)["pb"][0]
    (ROOT / "app" / "data" / "maps_pb.txt").write_text(pb.split("!7i20", 1)[1] + "\n", "utf-8")

    data = decode(captured["body"])
    small = [None] * len(data)
    small[1], small[64] = data[1], data[64][:4]
    (ROOT / "tests" / "fixtures" / "maps_page.json").write_text(
        json.dumps(small, ensure_ascii=False), "utf-8")
    print("Saved. Run the tests; update tests/test_core.py if the first places changed.")


if __name__ == "__main__":
    main()
