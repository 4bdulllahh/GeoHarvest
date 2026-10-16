"""New search: what to look for, where, which businesses, and the run itself."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QCompleter, QHBoxLayout, QLineEdit, QSpinBox, QWidget

from app.core import db, geo
from app.core import search as searches
from app.ui.pages.base import Page
from app.ui.widgets.common import (Card, ChoiceButtons, FormRow, ProgressRow, Section, StatTile,
                                   confirm_button, danger_button, hint, muted, row,
                                   secondary_button)
from app.ui.widgets.inputs import checkbox, combo, line_edit

NICHES = [
    "accountant", "advertising agency", "architect", "auto repair shop", "bakery", "bank",
    "barber shop", "beauty salon", "bookstore", "builder", "business consultant", "cafe",
    "car dealer", "car rental", "carpenter", "catering", "chiropractor", "cleaning service",
    "clothing store", "coffee shop", "construction company", "consultancy", "coworking space",
    "dentist", "digital marketing agency", "doctor", "electrician", "electronics store",
    "event planner", "fitness center", "florist", "furniture store", "gas station",
    "graphic designer", "grocery store", "gym", "hair salon", "hardware store",
    "home builder", "hospital", "hotel", "HVAC contractor", "insurance agency",
    "interior designer", "IT company", "jewelry store", "language school", "laundry",
    "law firm", "lawyer", "logistics company", "manufacturer", "marketing agency",
    "medical clinic", "mobile phone store", "moving company", "nail salon", "optician",
    "painter", "pest control", "pet store", "pharmacy", "photographer", "physiotherapist",
    "pizza restaurant", "plumber", "printing service", "private school", "property management",
    "real estate agency", "recruitment agency", "restaurant", "roofing contractor",
    "school", "security company", "shoe store", "software company", "solar energy company",
    "spa", "supermarket", "tailor", "tattoo shop", "travel agency", "tutoring service",
    "university", "veterinarian", "web design company", "wedding venue", "wholesaler",
    "yoga studio",
]


class ListCompleter(QCompleter):
    """Completes the last entry of a comma-separated list, keeping the ones before it."""

    def splitPath(self, path: str) -> list[str]:  # noqa: N802 - Qt naming
        return [path.split(",")[-1].strip()]

    def pathFromIndex(self, index) -> str:  # noqa: N802 - Qt naming
        typed = self.widget().text()
        before = typed.rsplit(",", 1)[0] + ", " if "," in typed else ""
        return before + super().pathFromIndex(index) + ", "


def list_input(placeholder: str, options: list[str]) -> QLineEdit:
    edit = line_edit(placeholder)
    completer = ListCompleter(options, edit)
    completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    completer.setFilterMode(Qt.MatchFlag.MatchContains)
    completer.setMaxVisibleItems(10)
    edit.setCompleter(completer)
    return edit


def split_list(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


def spin(low: int, high: int, value: int, suffix: str = "", special: str = "") -> QSpinBox:
    box = QSpinBox()
    box.setRange(low, high)
    box.setValue(value)
    box.setSuffix(suffix)
    if special:
        box.setSpecialValueText(special)
    box.setFixedWidth(150)
    return box


class SearchPage(Page):
    def __init__(self, window):
        super().__init__(window)
        self.worker = None
        self.search_id: int | None = None
        self.add_header("New search", "Pick a kind of business and a place. GeoHarvest finds every "
                                      "match on Google Maps, with phone, website, address and more.")
        body = self.scroll_body()
        layout = body.body_layout
        last = searches.options_with_defaults(db.get_setting("last_options", {}))

        # --- what -----------------------------------------------------------
        what = Section("What are you looking for?",
                       "Type it the way you would into Google Maps. Separate several with commas.")
        self.niches = list_input("For example: dentist, real estate agency, coffee shop", NICHES)
        self.niches.setText(", ".join(last["niches"]))
        what.add(self.niches)
        layout.addWidget(what)

        # --- where ----------------------------------------------------------
        where = Section("Where?")
        country_row = FormRow("Country")
        self.country = combo([""] + geo.countries(), last["country"], translate=False)
        self.country.setEditable(True)
        self.country.lineEdit().setPlaceholderText("Start typing a country")
        self.country.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.country.completer().setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.country.setFixedWidth(320)
        self.country.currentTextChanged.connect(self._country_changed)
        country_row.add(self.country)
        where.add(country_row)

        cities_row = FormRow("Cities (optional)",
                             "Leave empty to search the country's biggest cities one by one. "
                             "Google shows about 200 businesses per city, so more cities means "
                             "more leads.")
        self.cities = list_input("For example: Lahore, Karachi", [])
        self.cities.setText(", ".join(last["cities"]))
        cities_row.add(self.cities)
        self.city_count = spin(1, 60, int(last["city_count"]), " cities")
        cities_row.add(row(muted("If empty, search the biggest", wrap=False), self.city_count,
                           None))
        where.add(cities_row)
        layout.addWidget(where)
        self._country_changed(self.country.lineEdit().text())

        # --- which ----------------------------------------------------------
        which = Section("Which businesses?")
        age_row = FormRow("Company age",
                          "Estimated from when the business's website was registered (or first "
                          "appeared online, for countries whose registry keeps that private, "
                          "which takes longer). Google Maps does not record when a company was "
                          "founded, so businesses without a website only appear under Any age.")
        self.company_age = ChoiceButtons(
            [("any", "Any age"), ("startup", "Startups (under 3 years)"),
             ("established", "Established (3 years or more)")], last["company_age"])
        age_row.add(self.company_age)
        which.add(age_row)

        rating_row = FormRow("Google rating")
        self.min_rating = ChoiceButtons(
            [("0", "Any rating"), ("3.5", "3.5 and up"), ("4", "4 and up"), ("4.5", "4.5 and up")],
            str(last["min_rating"]).removesuffix(".0"))
        rating_row.add(self.min_rating)
        which.add(rating_row)

        self.min_reviews = spin(0, 100000, int(last["min_reviews"]), " reviews", "Any")
        self.max_results = spin(0, 100000, int(last["max_results"]), " leads", "No limit")
        limits = QWidget()
        limits_layout = QHBoxLayout(limits)
        limits_layout.setContentsMargins(0, 0, 0, 0)
        limits_layout.setSpacing(12)
        for label, box in (("At least", self.min_reviews), ("Stop after", self.max_results)):
            field = FormRow(label, "Counted before the company age check" if box is
                            self.max_results else "")
            field.add(box)
            limits_layout.addWidget(field)
        limits_layout.addStretch(1)
        which.add(limits)

        self.require_website = checkbox("Must have a website", last["require_website"])
        self.require_phone = checkbox("Must have a phone number", last["require_phone"])
        self.skip_closed = checkbox("Leave out closed businesses", last["skip_closed"])
        self.skip_known = checkbox("Leave out businesses I found in earlier searches",
                                   last["skip_known"])
        for box in (self.require_website, self.require_phone, self.skip_closed, self.skip_known):
            which.add(box)
        layout.addWidget(which)

        # --- extra ----------------------------------------------------------
        extra = Section("Extra detail")
        self.find_emails = checkbox(
            "Visit each website to find emails and social media (Facebook, Instagram, "
            "LinkedIn...) and estimate company age", last["find_emails"])
        extra.add(self.find_emails)
        self.smart = checkbox("Smart mode: let AI check every lead against your ideal customer",
                              last["smart"])
        extra.add(self.smart)
        self.smart_note = hint("")
        extra.add(self.smart_note)
        layout.addWidget(extra)
        layout.addStretch(1)

        # --- run bar (stays visible below the scrolling form) ---------------
        bar = Card(padding=14)
        stats = QHBoxLayout()
        stats.setSpacing(10)
        self.tile_leads = StatTile("Leads found", "0")
        self.tile_places = StatTile("Searches done", "0")
        self.tile_web = StatTile("Websites checked", "-")
        self.tile_email = StatTile("With an email", "0")
        self.tile_phone = StatTile("With a phone", "0")
        for tile in (self.tile_leads, self.tile_places, self.tile_web, self.tile_email,
                     self.tile_phone):
            stats.addWidget(tile)
        self.stats = QWidget()
        self.stats.setLayout(stats)
        self.stats.hide()
        bar.add(self.stats)

        self.progress = ProgressRow()
        self.progress.hide()
        bar.add(self.progress)
        self.status = muted("Ready when you are.", wrap=False)
        self.start_button = confirm_button("Start search", self.start)
        self.stop_button = danger_button("Stop", self.stop)
        self.stop_button.hide()
        self.open_button = secondary_button("Open leads", self.open_leads)
        self.open_button.hide()
        bar.add(row(self.status, self.open_button, self.stop_button, self.start_button, stretch=0))
        self.root.addWidget(bar)

    # --- form ---------------------------------------------------------------
    def _country_changed(self, country: str) -> None:
        completer = self.cities.completer()
        completer.model().setStringList(geo.cities(country))

    def on_show(self) -> None:
        ready = bool(db.get_setting("ai_provider", ""))
        self.smart.setEnabled(ready)
        if not ready:
            self.smart.setChecked(False)
        self.smart_note.setText("" if ready else
                                "Set up Smart mode first: open Smart mode in the menu and add a "
                                "free AI key or a local model.")

    def options(self) -> dict:
        return {
            "niches": split_list(self.niches.text()),
            "country": self.country.lineEdit().text().strip(),
            "cities": split_list(self.cities.text()),
            "city_count": self.city_count.value(),
            "company_age": self.company_age.get(),
            "min_rating": float(self.min_rating.get()),
            "min_reviews": self.min_reviews.value(),
            "max_results": self.max_results.value(),
            "require_website": self.require_website.isChecked(),
            "require_phone": self.require_phone.isChecked(),
            "skip_closed": self.skip_closed.isChecked(),
            "skip_known": self.skip_known.isChecked(),
            "find_emails": self.find_emails.isChecked(),
            "smart": self.smart.isChecked(),
        }

    def _validate(self, options: dict) -> str | None:
        if not options["niches"]:
            return "Type what kind of business you are looking for."
        if not options["country"] and not options["cities"]:
            return "Pick a country, or type at least one city."
        if options["country"] and options["country"] not in geo.countries():
            return "Pick the country from the list, so GeoHarvest knows its cities."
        return None

    # --- running ------------------------------------------------------------
    def start(self) -> None:
        options = self.options()
        problem = self._validate(options)
        if problem:
            self.notify(problem, "warn")
            return
        db.set_setting("last_options", options)
        self.run(searches.create(options))

    def run(self, search_id: int) -> None:
        """Start (or resume) a saved search."""
        from app.workers.scrape import ScrapeWorker

        if self.worker is not None:
            return
        self.search_id = search_id
        record = searches.get(search_id)
        self.total_queries = len(searches.build_queries(record["options"]))
        self.counts = {"leads": 0, "email": 0, "phone": 0}
        self.known: dict[str, dict] = {}  # what each lead added to the tiles, to undo on removal
        self.queries_done = len(record["progress"].get("done", []))
        self.tile_web.update_value("-")
        for lead in searches.leads(search_id):
            self._count(lead)
        self._show_counts()

        self.worker = ScrapeWorker(search_id)
        self.worker.signals.leads.connect(self._on_leads)
        self.worker.signals.updated.connect(self._on_updated)
        self.worker.signals.removed.connect(self._on_removed)
        self.worker.signals.checked.connect(self._on_checked)
        self.worker.signals.progress.connect(self._on_progress)
        self.worker.signals.message.connect(lambda text, level: self.notify(text, level))
        self.worker.signals.finished.connect(self._on_finished)
        self.worker.signals.failed.connect(self._on_failed)
        self._set_running(True)
        self.status.setText(f"Searching: {record['title']}")
        self.worker.start()

    def stop(self) -> None:
        if self.worker is not None:
            self.worker.stop()
            self.stop_button.setEnabled(False)
            self.stop_button.setText("Stopping...")

    def _set_running(self, running: bool) -> None:
        self.start_button.setVisible(not running)
        self.stop_button.setVisible(running)
        self.stop_button.setEnabled(True)
        self.stop_button.setText("Stop")
        self.open_button.setVisible(True)
        self.stats.show()
        self.progress.setVisible(running)
        if running:
            self.progress.set_busy()
        self.window_.set_status(left="Searching..." if running else "")

    def _count(self, lead: dict) -> None:
        added = {"email": bool(lead.get("emails")), "phone": bool(lead.get("phone"))}
        self.known[lead["place_id"]] = added
        self.counts["leads"] += 1
        self.counts["email"] += added["email"]
        self.counts["phone"] += added["phone"]

    def _show_counts(self) -> None:
        self.tile_leads.update_value(f"{self.counts['leads']:,}")
        self.tile_places.update_value(f"{self.queries_done} of {self.total_queries}")
        self.tile_email.update_value(f"{self.counts['email']:,}")
        self.tile_phone.update_value(f"{self.counts['phone']:,}")

    def _on_leads(self, leads: list) -> None:
        for lead in leads:
            self._count(lead)
        self._show_counts()
        self.window_.leads_added.emit(self.search_id, leads)
        self.window_.refresh_status()

    def _on_progress(self, done: int, total: int, detail: str) -> None:
        self.progress.set_progress(done, total)
        self.queries_done = done
        self._show_counts()
        if detail and detail != "Starting":
            self.status.setText(f"Finished: {detail}")

    def _on_updated(self, place_id: str, fields: dict) -> None:
        added = self.known.get(place_id)
        if fields.get("emails") and added is not None and not added["email"]:
            added["email"] = True
            self.counts["email"] += 1
            self._show_counts()
        self.window_.lead_updated.emit(self.search_id, place_id, fields)

    def _on_removed(self, place_id: str) -> None:
        added = self.known.pop(place_id, {"email": False, "phone": False})
        self.counts["leads"] -= 1
        self.counts["email"] -= added["email"]
        self.counts["phone"] -= added["phone"]
        self._show_counts()
        self.window_.lead_removed.emit(self.search_id, place_id)

    def _on_checked(self, done: int, total: int) -> None:
        self.tile_web.update_value(f"{done:,} of {total:,}")
        if self.queries_done == self.total_queries and done < total:
            self.status.setText(f"Searching done. Checking websites: {done:,} of {total:,}")

    def _on_finished(self, result: dict) -> None:
        self.worker = None
        self._set_running(False)
        found = self.counts["leads"]
        if result["blocked"]:
            self.status.setText("Paused: Google is limiting requests from your connection.")
            self.notify("Google asked GeoHarvest to slow down. Everything found so far is saved. "
                        "Wait about 15 minutes, then resume it from Past searches.", "warn", 10000)
        elif result["status"] == "done":
            self.queries_done = self.total_queries  # also true when "Stop after" ended it early
            self._show_counts()
            self.status.setText(f"Done. {found:,} leads found.")
            self.notify(f"Search finished: {found:,} leads.", "success")
        else:
            self.status.setText(f"Stopped. {found:,} leads saved; resume it from Past searches.")
        self.window_.search_finished.emit(self.search_id)
        self.window_.refresh_status()

    def _on_failed(self, message: str) -> None:
        self.worker = None
        self._set_running(False)
        if self.search_id is not None:
            searches.set_status(self.search_id, "stopped")
        self.status.setText("The search stopped because of an error.")
        self.notify(f"The search stopped: {message}", "error", 8000)

    def open_leads(self) -> None:
        self.window_.show_page("leads")
        page = self.window_.page("leads")
        if page is not None and self.search_id is not None:
            page.select_search(self.search_id)

    def busy_reason(self) -> str | None:
        return "a search is running" if self.worker is not None else None
