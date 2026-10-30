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

from PyQt6.QtCore import QPoint, Qt, QTimer  # noqa: E402
from PyQt6.QtGui import QPainter  # noqa: E402
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

# Made-up people for the made-up businesses
OWNERS = ["Dr. Omar Rahman", "Dr. Anna Becker", "Dr. James Carter", "Dr. Layla Haddad",
          "Dr. Priya Nair", "Dr. Lukas Weber", "Dr. Maria Lopez"]
HOURS = ("Monday: 9 AM-8 PM; Tuesday: 9 AM-8 PM; Wednesday: 9 AM-8 PM; Thursday: 9 AM-8 PM; "
         "Friday: 2-9 PM; Saturday: 10 AM-6 PM; Sunday: Closed")
TIMEZONES = {"Dubai": "Asia/Dubai", "Abu Dhabi": "Asia/Dubai", "New York": "America/New_York",
             "Austin": "America/Chicago", "Berlin": "Europe/Berlin"}
# The columns the README's main picture shows
HERO_COLUMNS = ["name", "ai_score", "ai_tag", "ai_reason", "owner_name", "phone", "emails",
                "rating", "reviews", "city"]
OPENERS = ["Loved the reviews about your friendly team. Have you thought about online booking?",
           "Your clinic's 4.8 stars stand out in {city}; a faster website could show it off.",
           "Saw you opened recently in {city}: congratulations! Quick idea for new patients."]


def demo_leads(count: int = 60) -> list[dict]:
    rng = random.Random(7)
    leads = []
    for i in range(count):
        city, code, phone, area = PLACES[i % len(PLACES)]
        name = f"{FIRST[i % len(FIRST)]} {KIND[(i // len(FIRST) + i) % len(KIND)]}"  # all different
        slug = name.lower().replace(" ", "")
        score = rng.choice([92, 88, 85, 81, 76, 64, 58, 41, 33])
        verdict = "Good fit" if score >= 80 else "Maybe" if score >= 50 else "Poor fit"
        tag = {"Good fit": "Hot", "Maybe": "Warm", "Poor fit": "Cold"}[verdict]
        years = rng.choice([1, 2, 4, 7, 11, 15])
        leads.append({
            "place_id": f"demo{i}", "name": name, "category": "Dentist",
            "ai_score": score, "ai_verdict": verdict, "ai_reason": rng.choice(REASONS[verdict]),
            "ai_tag": tag, "ai_opener": rng.choice(OPENERS).format(city=city),
            "ai_channel": rng.choice(["Email", "Phone", "WhatsApp", "Instagram"]),
            "phone": phone.format(100 + i), "phone_international": phone.format(100 + i),
            "emails": f"hello@{slug}.example",
            "website": f"https://{slug}.example", "domain": f"{slug}.example",
            "instagram": f"https://instagram.com/{slug}" if i % 3 else "",
            "facebook": f"https://facebook.com/{slug}" if i % 2 else "",
            "rating": round(rng.uniform(3.9, 5.0), 1), "reviews": rng.randint(12, 900),
            "company_age": f"{'Startup' if years < 3 else 'Established'} ({years} "
                           f"year{'s' if years > 1 else ''})",
            "status": "Open", "address": f"{10 + i} Example Street, {area}, {city}",
            "neighborhood": area, "city": city, "country_code": code, "claimed": "Yes",
            "maps_url": "https://maps.google.com", "query": f"dentist in {city}", "enriched": True,
            "hours": HOURS, "timezone": TIMEZONES[city],
        })
        if i % 3 != 2:
            owner = OWNERS[i % len(OWNERS)]
            leads[-1].update(owner_name=owner, owner_source="Website" if i % 4 else
                             "Domain record", owner_linkedin="https://www.linkedin.com/in/"
                             + owner.removeprefix("Dr. ").lower().replace(" ", "-") + "-example"
                             if i % 4 else "N/A")
    return leads


def main() -> None:
    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    from app.core import db
    from app.core import search as searches
    from app.ui import theme
    from app.ui.main_window import MainWindow
    from app.ui.pages.leads import ColumnsDialog, LeadDialog
    from app.ui.widgets.common import ScrollPage

    db.init()
    countries = ["United Arab Emirates", "United States", "Germany"]
    sid = searches.create({"niches": ["dentist"], "countries": countries,
                           "cities": ["Dubai, United Arab Emirates",
                                      "Abu Dhabi, United Arab Emirates",
                                      "New York City, United States", "Austin, United States",
                                      "Berlin, Germany"], "smart": True, "find_owner": True,
                           "fields": HERO_COLUMNS})
    searches.save_leads(sid, demo_leads())
    searches.set_status(sid, "done")
    other = searches.create({"niches": ["real estate agency"], "where": "area",
                             "area_place": "Downtown Dubai", "area_km": 5, "area_lat": 25.19,
                             "area_lng": 55.27})
    searches.save_leads(other, [{**lead, "place_id": f"re{i}"} for i, lead in
                                enumerate(demo_leads(25))])
    searches.set_status(other, "stopped")
    db.set_setting("ai_provider", "gemini")
    db.set_setting("ai_profile", "Independent dental clinics with a website but little social "
                                 "media, who might want help getting more patients online.")
    db.set_setting("ai_dealbreakers", "Hospital departments and big dental chains")
    db.set_setting("ai_profiles", {
        "Dentists for SEO": {"profile": "Dental clinics with few reviews.", "never": ""},
        "Clinics for booking app": {"profile": "Clinics that book by phone only.", "never": ""}})
    for key in ("ai_opener", "ai_needs", "ai_channel", "ai_contact_only"):
        db.set_setting(key, True)
    db.set_setting("ai_per_minute", 12)
    db.set_setting("ai_max_leads", 300)
    db.set_setting("last_options", {
        "niches": ["dentist", "dental clinic"], "where": "area", "area_place": "Dubai Marina",
        "area_km": 5, "max_reviews": 150, "open_weekends": True, "find_emails": True,
        "find_owner": True, "min_leads": 100, "max_leads": 300})

    theme.apply_preferences()
    app.setStyleSheet(theme.stylesheet())
    window = MainWindow()
    window.resize(1440, 900)
    window.show()
    out = ROOT / "docs" / "screenshots"
    out.mkdir(parents=True, exist_ok=True)

    def save_window(name: str) -> None:
        window.grab().save(str(out / f"{name}.png"))

    def scroll_to(page, widget, margin: int) -> None:
        page.findChild(ScrollPage).ensureWidgetVisible(widget, 0, margin)

    def leads_page():
        window.show_page("leads")
        page = window.page("leads")
        page.select_search(sid)
        page.table.view.sortByColumn(1, Qt.SortOrder.DescendingOrder)
        # Narrower columns (long text is cut short with "...") so the contact columns fit too
        widths = {"name": 190, "ai_score": 80, "ai_tag": 80, "ai_reason": 220,
                  "owner_name": 135, "phone": 135, "emails": 245}
        QTimer.singleShot(100, lambda: [page.table.view.setColumnWidth(
            page.model.keys.index(key), width) for key, width in widths.items()])

    def search_filters():
        window.show_page("search")
        page = window.page("search")
        scroll_to(page, page.max_leads, 260)

    def smart_extras():
        window.show_page("smart")
        page = window.page("smart")
        scroll_to(page, page.contact_only, 40)

    def search_running():
        window.show_page("search")
        page = window.page("search")
        page.findChild(ScrollPage).verticalScrollBar().setValue(0)
        page.stats.show()
        page.progress.show()
        page.progress.set_progress(358, 400)
        page.tile_found.update_value("412")
        page.tile_places.update_value("9 of 16")
        page.tile_web.update_value("358 of 400")
        page.tile_email.update_value("201")
        page.tile_phone.update_value("377")
        page.tile_ai.hide()
        page.tile_best.update_value("118 of 300")
        page.status.setText("Step 2 of 3: Checking websites")
        page.start_button.hide()
        page.stop_button.show()

    def leads_exports():
        """The Leads page with the More exports menu open, drawn into one picture."""
        leads_page()
        page = window.page("leads")
        menu = page.csv_button.menu()
        menu.popup(page.csv_button.mapToGlobal(QPoint(0, page.csv_button.height())))
        QTimer.singleShot(300, lambda: (paint_menu(menu), menu.close()))

    def paint_menu(menu) -> None:
        picture = window.grab()
        painter = QPainter(picture)
        painter.drawPixmap(window.mapFromGlobal(menu.pos()), menu.grab())
        painter.end()
        picture.save(str(out / "exports.png"))

    def dialog_shot(name: str, dialog) -> None:
        dialog.show()
        QTimer.singleShot(300, lambda: (dialog.grab().save(str(out / f"{name}.png")),
                                        dialog.close()))

    def history_loaded():
        window.show_page("history")
        page = window.page("history")
        page.table.view.selectRow(0)
        page.load()

    def settings_proxies():
        window.show_page("settings")
        page = window.page("settings")
        # Documentation-only addresses (RFC 5737), shown in the box but never saved
        page.proxies.setPlainText("203.0.113.10:8080\nuser:password@203.0.113.25:3128\n"
                                  "socks5://198.51.100.7:1080")
        page.proxy_status.setText("3 of 3 working.")
        scroll_to(page, page.proxies, 200)

    lead = next(lead for lead in demo_leads() if lead["place_id"] == "demo0")
    shots = [
        ("search", lambda: window.show_page("search"), save_window),
        ("filters", search_filters, save_window),
        ("search-running", search_running, save_window),
        ("leads", leads_page, save_window),
        ("exports", leads_exports, None),
        ("lead", lambda: dialog_shot("lead", LeadDialog(window, lead)), None),
        ("columns", lambda: dialog_shot("columns", ColumnsDialog(
            window, set(HERO_COLUMNS), {"price", "photo"}, lambda _chosen: None)), None),
        ("smart", lambda: window.show_page("smart"), save_window),
        ("smart-extras", smart_extras, save_window),
        ("settings", settings_proxies, save_window),
        ("history", history_loaded, save_window),  # last: its toast would show on later shots
    ]

    def shoot(index: int = 0) -> None:
        if index >= len(shots):
            app.quit()
            return
        name, show, save = shots[index]
        show()
        QTimer.singleShot(700, lambda: (save(name) if save else None, shoot(index + 1)))

    QTimer.singleShot(800, shoot)
    app.exec()
    print(f"Saved {len(shots)} screenshots to {out}")


if __name__ == "__main__":
    main()
