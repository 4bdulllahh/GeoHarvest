"""Save README screenshots of every page to docs/screenshots/, using made-up demo data.

    python tools/screenshot.py

Runs against a throwaway data folder filled with fictional businesses (.example
domains, 555 phone numbers), so no real business or person appears in the docs
and the user's own data is never touched.
"""
import os
import random
import sys
import tempfile
from pathlib import Path

os.environ["APPDATA"] = tempfile.mkdtemp(prefix="geoharvest-demo-")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import Qt, QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

FIRST = ["Bright", "Harbour", "Cedar", "Palm", "Summit", "Blue Lagoon", "Golden", "Oakwood",
         "Marina", "Desert Rose", "Northside", "Riverside", "Crescent", "Lakeview", "Parkside",
         "Silver Line", "Greenleaf", "Sunrise", "Old Town", "Westgate"]
KIND = ["Dental Clinic", "Dental Care", "Smile Studio", "Family Dentistry", "Dental Centre"]
PLACES = [("Dubai", "AE", "+971 4 555 {:04d}", "Jumeirah"), ("Abu Dhabi", "AE", "+971 2 555 {:04d}",
          "Al Reem"), ("New York", "US", "+1 212-555-{:04d}", "Midtown"),
          ("Austin", "US", "+1 512-555-{:04d}", "Downtown"), ("Berlin", "DE", "+49 30 555 {:04d}",
          "Mitte")]
REASONS = {
    "Good fit": ["Independent clinic, strong reviews, website but no Instagram: likely open to "
                 "marketing help.", "Owner-run practice with a dated website and few reviews "
                 "replied to.", "Growing clinic, 4.8 stars, no booking link on the site."],
    "Maybe": ["Part of a small group; decisions may sit at head office.",
              "Good reviews but already very active on social media."],
    "Poor fit": ["Hospital department rather than a clinic.", "Listing looks closed: no reviews "
                 "this year and the website is offline."],
}


def demo_leads(count: int = 60) -> list[dict]:
    rng = random.Random(7)
    leads = []
    for i in range(count):
        city, code, phone, area = PLACES[i % len(PLACES)]
        name = f"{FIRST[i % len(FIRST)]} {KIND[i % len(KIND)]}"
        slug = name.lower().replace(" ", "")
        score = rng.choice([92, 88, 85, 81, 76, 64, 58, 41, 33])
        verdict = "Good fit" if score >= 80 else "Maybe" if score >= 50 else "Poor fit"
        years = rng.choice([1, 2, 4, 7, 11, 15])
        leads.append({
            "place_id": f"demo{i}", "name": name, "category": "Dentist",
            "ai_score": score, "ai_verdict": verdict, "ai_reason": rng.choice(REASONS[verdict]),
            "phone": phone.format(100 + i), "emails": f"hello@{slug}.example",
            "website": f"https://{slug}.example", "domain": f"{slug}.example",
            "instagram": f"https://instagram.com/{slug}" if i % 3 else "",
            "facebook": f"https://facebook.com/{slug}" if i % 2 else "",
            "rating": round(rng.uniform(3.9, 5.0), 1), "reviews": rng.randint(12, 900),
            "company_age": f"{'Startup' if years < 3 else 'Established'} ({years} "
                           f"year{'s' if years > 1 else ''})",
            "status": "Open", "address": f"{10 + i} Example Street, {area}, {city}",
            "neighborhood": area, "city": city, "country_code": code, "claimed": "Yes",
            "maps_url": "https://maps.google.com", "query": f"dentist in {city}", "enriched": True,
        })
    return leads


def main() -> None:
    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    from app.core import db
    from app.core import search as searches
    from app.ui import theme
    from app.ui.main_window import MainWindow

    db.init()
    countries = ["United Arab Emirates", "United States", "Germany"]
    sid = searches.create({"niches": ["dentist"], "countries": countries,
                           "cities": ["Dubai, United Arab Emirates",
                                      "Abu Dhabi, United Arab Emirates",
                                      "New York City, United States", "Austin, United States",
                                      "Berlin, Germany"], "smart": True})
    searches.save_leads(sid, demo_leads())
    searches.set_status(sid, "done")
    other = searches.create({"niches": ["real estate agency"], "countries": ["Gulf (GCC)"],
                             "city_count": 3})
    searches.save_leads(other, [{**lead, "place_id": f"re{i}"} for i, lead in
                                enumerate(demo_leads(25))])
    searches.set_status(other, "stopped")
    db.set_setting("ai_provider", "gemini")
    db.set_setting("ai_profile", "Independent dental clinics with a website but little social "
                                 "media, who might want help getting more patients online.")
    db.set_setting("last_options", {"niches": ["dentist"], "countries": countries,
                                    "cities": ["Dubai, United Arab Emirates",
                                               "New York City, United States", "Berlin, Germany"],
                                    "find_emails": True})

    theme.apply_preferences()
    app.setStyleSheet(theme.stylesheet())
    window = MainWindow()
    window.resize(1440, 900)
    window.show()
    out = ROOT / "docs" / "screenshots"
    out.mkdir(parents=True, exist_ok=True)

    def leads_page():
        window.show_page("leads")
        window.page("leads").select_search(sid)
        view = window.page("leads").table.view
        view.sortByColumn(1, Qt.SortOrder.DescendingOrder)

    def search_running():
        window.show_page("search")
        page = window.page("search")
        page.stats.show()
        page.progress.show()
        page.progress.set_progress(3, 5)
        page.tile_leads.update_value("612")
        page.tile_places.update_value("3 of 5")
        page.tile_web.update_value("498 of 571")
        page.tile_email.update_value("344")
        page.tile_phone.update_value("590")
        page.tile_ai.update_value("480 of 498")
        page.status.setText("Searching: dentist in 5 cities in United Arab Emirates, "
                            "United States, Germany")
        page.start_button.hide()
        page.stop_button.show()

    shots = [("search", lambda: window.show_page("search")), ("search-running", search_running),
             ("leads", leads_page), ("history", lambda: window.show_page("history")),
             ("smart", lambda: window.show_page("smart")),
             ("settings", lambda: window.show_page("settings"))]

    def shoot(index: int = 0) -> None:
        if index >= len(shots):
            app.quit()
            return
        name, show = shots[index]
        show()
        QTimer.singleShot(500, lambda: (window.grab().save(str(out / f"{name}.png")),
                                        shoot(index + 1)))

    QTimer.singleShot(800, shoot)
    app.exec()
    print(f"Saved {len(shots)} screenshots to {out}")


if __name__ == "__main__":
    main()
