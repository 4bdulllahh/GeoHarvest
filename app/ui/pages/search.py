"""New search: what to look for, where, which businesses, and the run itself."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QCompleter, QHBoxLayout, QLineEdit, QSpinBox, QWidget

from app.core import db, geo, hours, scraper
from app.core import search as searches
from app.ui.pages.base import Page
from app.core.places import FIELD_GROUPS, HEADERS
from app.ui.widgets.common import (Card, small_button, ChoiceButtons, FormRow, ProgressRow, Section, StatTile,
                                   confirm_button, danger_button, flow_row, hint, muted, row,
                                   secondary_button)
from app.ui.widgets.checklist import CheckList
from app.ui.widgets.inputs import checkbox, combo, line_edit
from app.workers.base import Task

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

# Filled in only by visiting the business's website
FROM_WEBSITE = {"emails", "facebook", "instagram", "linkedin", "twitter", "youtube", "tiktok",
                "company_age", "domain_created", "age_source", "owner_name", "owner_source",
                "owner_linkedin"}
TIMES = [f"{hour:02d}:{minute:02d}" for hour in range(24) for minute in (0, 30)]
RATINGS = [("3.5", "3.5"), ("4", "4"), ("4.5", "4.5")]


class ListCompleter(QCompleter):
    """Completes the last entry of a comma-separated list, keeping the ones before it."""

    def splitPath(self, path: str) -> list[str]:  # noqa: N802 - Qt naming
        return [path.split(",")[-1].strip()]

    def pathFromIndex(self, index) -> str:  # noqa: N802 - Qt naming
        # Replaces only the last entry. No ", " here: Qt writes this in on highlight too, and
        # a finished entry would make the click that follows add the choice a second time.
        typed = self.widget().text()
        before = typed.rsplit(",", 1)[0] + ", " if "," in typed else ""
        return before + super().pathFromIndex(index)


def list_input(placeholder: str, options: list[str]) -> QLineEdit:
    edit = line_edit(placeholder)
    completer = ListCompleter(options, edit)
    # Ready for the next entry once a suggestion is picked (after Qt has written it in)
    completer.activated.connect(lambda _text: QTimer.singleShot(
        0, lambda: edit.setText(edit.text().rstrip(", ") + ", ")))
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
        where = Section("Where?",
                        "Search whole countries city by city, or everything within a distance "
                        "of one place.")
        self.where = ChoiceButtons([("cities", "Countries and cities"),
                                    ("area", "Around a place")], last["where"],
                                   on_change=lambda _key: self._where_changed())
        where.add(self.where)
        self.countries = CheckList("Search countries")
        self.countries.set_items([(r, f"{r} (all its countries)") for r in geo.REGIONS]
                                 + [(c, c) for c in geo.countries()], set())
        self.cities = CheckList("Search cities")
        self.extra_places: list[str] = []
        self.extra_place = line_edit("A town or area that is not listed")
        self.extra_place.returnPressed.connect(self._add_place)
        self.cities_box = QWidget()
        self.cities_box.setProperty("role", "plain")
        columns = QHBoxLayout(self.cities_box)
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(16)
        left, right = FormRow("Countries"), FormRow("Cities")
        left.add(self.countries)
        right.add(self.cities)
        right.add(row(self.extra_place, small_button("Add", self._add_place), stretch=0))
        columns.addWidget(left, 1, Qt.AlignmentFlag.AlignTop)
        columns.addWidget(right, 1, Qt.AlignmentFlag.AlignTop)
        where.add(self.cities_box)

        self.area_box = QWidget()
        self.area_box.setProperty("role", "plain")
        area = QHBoxLayout(self.area_box)
        area.setContentsMargins(0, 0, 0, 0)
        area.setSpacing(12)
        self.area_place = line_edit("For example: Dubai Marina, or 5th Avenue, New York")
        self.area_place.setText(last["area_place"])
        self.area_km = spin(1, 100, int(last["area_km"]), " km")
        place_row = FormRow("Place or address", "Type it the way you would into Google Maps.")
        place_row.add(self.area_place)
        km_row = FormRow("Within")
        km_row.add(self.area_km)
        area.addWidget(place_row, 1, Qt.AlignmentFlag.AlignTop)
        area.addWidget(km_row, 0, Qt.AlignmentFlag.AlignTop)
        where.add(self.area_box)
        # Where the place is on the map, once found: (typed text, latitude, longitude)
        self.located: tuple[str, float, float] | None = None
        self.city_count = int(last["city_count"])  # only for searches saved before city ticks
        self.plan = hint("")
        where.add(self.plan)
        layout.addWidget(where)
        self.countries.toggled.connect(self._country_toggled)
        self.countries.changed.connect(self._rebuild_cities)
        self.cities.changed.connect(self._update_plan)
        self.niches.textChanged.connect(self._update_plan)
        self.area_place.textChanged.connect(self._update_plan)
        self.area_km.valueChanged.connect(self._update_plan)

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

        ratings = QWidget()
        ratings_layout = QHBoxLayout(ratings)
        ratings_layout.setContentsMargins(0, 0, 0, 0)
        ratings_layout.setSpacing(24)
        self.min_rating = ChoiceButtons([("0", "Any")] + RATINGS,
                                        str(last["min_rating"]).removesuffix(".0"))
        self.max_rating = ChoiceButtons([("0", "Any")] + RATINGS,
                                        str(last["max_rating"]).removesuffix(".0"))
        for label, choice in (("Google rating at least", self.min_rating),
                              ("Google rating at most", self.max_rating)):
            field = FormRow(label)
            field.add(choice)
            ratings_layout.addWidget(field, 1, Qt.AlignmentFlag.AlignTop)
        which.add(ratings)

        self.min_reviews = spin(0, 100000, int(last["min_reviews"]), " reviews", "Any")
        self.max_reviews = spin(-1, 100000, int(last["max_reviews"]), " reviews", "No maximum")
        self.max_results = spin(0, 100000, int(last["max_results"]), " leads", "No limit")
        limits = QWidget()
        limits_layout = QHBoxLayout(limits)
        limits_layout.setContentsMargins(0, 0, 0, 0)
        limits_layout.setSpacing(12)
        for label, box, note in (
                ("Reviews at least", self.min_reviews, ""),
                ("Reviews at most", self.max_reviews, "Few reviews often means a business "
                                                      "that needs more customers"),
                ("Stop after", self.max_results, "You get exactly this many, if Google has "
                                                 "enough")):
            field = FormRow(label, note)
            field.add(box)
            limits_layout.addWidget(field, 0, Qt.AlignmentFlag.AlignTop)
        limits_layout.addStretch(1)
        which.add(limits)

        website_row = FormRow("Website", "\"No website\" finds businesses you could build a "
                                         "site for. Emails, social media, company age and the "
                                         "owner's name come from websites, so those stay empty.")
        self.website = ChoiceButtons([("any", "Any"), ("yes", "Has a website"),
                                      ("no", "No website")], last["website"])
        website_row.add(self.website)
        which.add(website_row)

        self.require_phone = checkbox("Must have a phone number", last["require_phone"])
        self.skip_closed = checkbox("Leave out closed businesses", last["skip_closed"])
        self.skip_known = checkbox("Leave out businesses I found in earlier searches",
                                   last["skip_known"])
        for box in (self.require_phone, self.skip_closed, self.skip_known):
            which.add(box)

        hours_row = FormRow("Opening hours", "In each business's own time zone. Businesses "
                                             "that don't list their hours on Google are left "
                                             "out while any of these is on.")
        self.open_now = checkbox("Open now", last["open_now"])
        self.open_24h = checkbox("Open 24 hours", last["open_24h"])
        self.open_weekends = checkbox("Open on weekends", last["open_weekends"])
        self.open_at = checkbox("Open on", last["open_at"])
        self.open_day = combo(hours.DAYS, hours.DAYS[int(last["open_day"])], translate=False)
        self.open_time = combo(TIMES, last["open_time"], translate=False)
        hours_row.add(self.open_now)
        hours_row.add(self.open_24h)
        hours_row.add(self.open_weekends)
        hours_row.add(row(self.open_at, self.open_day, muted("at", wrap=False), self.open_time,
                          None))
        which.add(hours_row)
        layout.addWidget(which)

        # --- extra ----------------------------------------------------------
        extra = Section("Extra detail")
        self.find_emails = checkbox(
            "Visit each website to find emails and social media (Facebook, Instagram, "
            "LinkedIn...) and estimate company age", last["find_emails"])
        extra.add(self.find_emails)
        self.find_owner = checkbox(
            "Look for the owner's name (on the website and in the domain record) and add a "
            "LinkedIn search link", last["find_owner"])
        extra.add(self.find_owner)
        self.smart = checkbox("Smart mode: let AI check every lead against your ideal customer",
                              last["smart"])
        extra.add(self.smart)
        self.smart_note = hint("")
        extra.add(self.smart_note)
        layout.addWidget(extra)

        # --- details ----------------------------------------------------------
        details = Section("Details to include",
                          "Switch off what you don't need. It is left out of the Leads table and "
                          "the Excel file. Name is always included.")
        self.detail_boxes: dict[str, object] = {}
        for group, keys in FIELD_GROUPS:
            container, flow = flow_row(spacing=14)
            for key in keys:
                box = checkbox(HEADERS[key], key in last["fields"] or key == "name")
                self.detail_boxes[key] = box
                flow.addWidget(box)
            group_row = FormRow(group)
            group_row.add(container)
            details.add(group_row)
        self.detail_boxes["name"].setEnabled(False)
        details.add(row(hint("Emails, social media, company age and the owner need \"Visit "
                             "each website\" switched on above."),
                        small_button("All on", lambda: self._tick_details(True)),
                        small_button("All off", lambda: self._tick_details(False)), stretch=0))
        layout.addWidget(details)
        self.find_emails.toggled.connect(self._website_details)
        self._website_details(self.find_emails.isChecked())
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
        self.tile_ai = StatTile("AI checked", "-")
        for tile in (self.tile_leads, self.tile_places, self.tile_web, self.tile_email,
                     self.tile_phone, self.tile_ai):
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
        self.load_options(last)

    # --- form ---------------------------------------------------------------
    def _country_toggled(self, key: str, on: bool) -> None:
        if key in geo.REGIONS:  # a region ticks or unticks all of its countries
            self.countries.set_checked(set(geo.expand([key])), on)

    def _chosen_countries(self) -> list[str]:
        return [c for c in self.countries.checked() if c not in geo.REGIONS]

    def _rebuild_cities(self, tick: set[str] | None = None) -> None:
        """List the cities of the ticked countries, keeping what was ticked.

        A country that just appeared starts with no cities ticked; ``tick`` says exactly
        what to tick when loading a saved search.
        """
        # A region shows as ticked only while every one of its countries is
        chosen = set(self._chosen_countries())
        for region in geo.REGIONS:
            self.countries.set_checked({region}, set(geo.expand([region])) <= chosen)
        keep = set(self.cities.checked()) if tick is None else set(tick)
        items = []
        for country in self._chosen_countries():
            names = geo.cities(country) or [country]
            for city in names:
                key = f"{city}, {country}" if city != country else country
                items.append((key, key))
        items += [(place, place) for place in self.extra_places]
        self.cities.set_items(items, keep)
        self._update_plan()

    def _add_place(self) -> None:
        place = self.extra_place.text().strip().strip(",")
        if not place:
            return
        countries = self._chosen_countries()
        if "," not in place and len(countries) == 1:
            place = f"{place}, {countries[0]}"
        if place not in self.extra_places:
            self.extra_places.append(place)
        self.extra_place.clear()
        self._rebuild_cities(tick=set(self.cities.checked()) | {place})

    def _where_changed(self) -> None:
        area = self.where.get() == "area"
        self.cities_box.setVisible(not area)
        self.area_box.setVisible(area)
        self._update_plan()

    def _update_plan(self) -> None:
        niches = split_list(self.niches.text())
        if self.where.get() == "area":
            count = len(searches.build_queries({
                "niches": niches, "where": "area", "area_place": self.area_place.text(),
                "area_km": self.area_km.value()}))
            self.plan.setText(f"{count:,} searches (the area is covered in small map views, one "
                              "search per view and business type)." if count else "")
            return
        count = len(searches.build_queries({
            "niches": niches, "countries": self._chosen_countries(),
            "cities": self.cities.checked()})) if self.cities.checked() else 0
        countries, cities = len(self._chosen_countries()), len(self.cities.checked())
        self.plan.setText(f"{countries} {'country' if countries == 1 else 'countries'}, "
                          f"{cities:,} {'city' if cities == 1 else 'cities'} chosen: "
                          f"{count:,} searches (one per city and business type)."
                          if count else "")

    def _tick_details(self, on: bool) -> None:
        for key, box in self.detail_boxes.items():
            box.setChecked(on or key == "name")

    def _website_details(self, on: bool) -> None:
        for key in FROM_WEBSITE:
            self.detail_boxes[key].setEnabled(on)
        self.find_owner.setEnabled(on)
        if not on:
            self.find_owner.setChecked(False)

    def on_show(self) -> None:
        ready = bool(db.get_setting("ai_provider", ""))
        self.smart.setEnabled(ready)
        if not ready:
            self.smart.setChecked(False)
        self.smart_note.setText("" if ready else
                                "Set up Smart mode first: open Smart mode in the menu and add a "
                                "free AI key or a local model.")

    def options(self) -> dict:
        place = self.area_place.text().strip()
        found = self.located if self.located and self.located[0] == place else None
        return {
            "niches": split_list(self.niches.text()),
            "where": self.where.get(),
            "area_place": place,
            "area_km": self.area_km.value(),
            "area_lat": found[1] if found else None,
            "area_lng": found[2] if found else None,
            "countries": self._chosen_countries(),
            "cities": self.cities.checked(),
            "city_count": self.city_count,
            "company_age": self.company_age.get(),
            "min_rating": float(self.min_rating.get()),
            "min_reviews": self.min_reviews.value(),
            "max_rating": float(self.max_rating.get()),
            "max_reviews": self.max_reviews.value(),
            "max_results": self.max_results.value(),
            "website": self.website.get(),
            "require_phone": self.require_phone.isChecked(),
            "open_now": self.open_now.isChecked(),
            "open_24h": self.open_24h.isChecked(),
            "open_weekends": self.open_weekends.isChecked(),
            "open_at": self.open_at.isChecked(),
            "open_day": hours.DAYS.index(self.open_day.currentText()),
            "open_time": self.open_time.currentText(),
            "skip_closed": self.skip_closed.isChecked(),
            "skip_known": self.skip_known.isChecked(),
            "find_emails": self.find_emails.isChecked(),
            "find_owner": self.find_owner.isChecked(),
            "smart": self.smart.isChecked(),
            "fields": [key for key, box in self.detail_boxes.items() if box.isChecked()],
        }

    def load_options(self, options: dict) -> None:
        """Fill the form from a saved search (Past searches: resume or run again)."""
        options = searches.options_with_defaults(options)
        self.niches.setText(", ".join(options["niches"]))
        self.where.set(options["where"])
        self.area_place.setText(options["area_place"])
        self.area_km.setValue(int(options["area_km"]))
        if options["area_lat"] is not None:
            self.located = (options["area_place"], options["area_lat"], options["area_lng"])
        self._where_changed()
        self.city_count = int(options["city_count"])
        countries = geo.expand(options["countries"])
        cities = searches.places_for(options)  # old saves: bare names, or none (biggest N)
        listed = {f"{c}, {country}" for country in countries for c in geo.cities(country)}
        self.extra_places = [c for c in cities if c not in listed and c not in countries]
        self.countries.set_checked(set(self.countries.keys()), False)
        self.countries.set_checked(set(countries))
        self._rebuild_cities(tick=set(cities))
        self.company_age.set(options["company_age"])
        self.min_rating.set(str(options["min_rating"]).removesuffix(".0"))
        self.max_rating.set(str(options["max_rating"]).removesuffix(".0"))
        self.min_reviews.setValue(int(options["min_reviews"]))
        self.max_reviews.setValue(int(options["max_reviews"]))
        self.max_results.setValue(int(options["max_results"]))
        self.website.set(options["website"])
        for name in ("require_phone", "skip_closed", "skip_known", "find_emails", "find_owner",
                     "open_now", "open_24h", "open_weekends", "open_at"):
            getattr(self, name).setChecked(bool(options[name]))
        self.open_day.setCurrentText(hours.DAYS[int(options["open_day"])])
        self.open_time.setCurrentText(options["open_time"])
        for key, box in self.detail_boxes.items():
            box.setChecked(key in options["fields"] or key == "name")
        self.on_show()  # Smart mode only stays ticked if it is still set up
        self.smart.setChecked(bool(options["smart"]) and self.smart.isEnabled())

    def _validate(self, options: dict) -> str | None:
        if not options["niches"]:
            return "Type what kind of business you are looking for."
        if options["where"] == "area":
            if not options["area_place"]:
                return "Type the place or address to search around."
        elif not options["cities"]:
            return "Choose at least one country and one city."
        if options["website"] == "no" and options["company_age"] != "any":
            return "Company age comes from the website, so it can't be used with \"No website\"."
        if options["max_rating"] and options["max_rating"] < options["min_rating"]:
            return "The highest rating is below the lowest one."
        if 0 <= options["max_reviews"] < options["min_reviews"]:
            return "\"Reviews at most\" is below \"Reviews at least\"."
        return None

    # --- running ------------------------------------------------------------
    def start(self) -> None:
        options = self.options()
        problem = self._validate(options)
        if problem:
            self.notify(problem, "warn")
            return
        if options["where"] == "area" and options["area_lat"] is None:
            self._locate_then_start(options["area_place"])
            return
        db.set_setting("last_options", options)
        self.run(searches.create(options))

    def _locate_then_start(self, place: str) -> None:
        """Find the typed place on Google Maps (a second or two), then start."""
        def locate():
            client = scraper.MapsClient()
            try:
                return scraper.locate(client, place)
            finally:
                client.close()

        def found(point) -> None:
            if point is None:
                self.status.setText("Ready when you are.")
                self.notify(f"Google Maps couldn't find \"{place}\". Try adding the city or "
                            "country.", "warn", 6000)
                return
            self.located = (place, *point)
            self.start()

        def failed(message: str) -> None:
            self.status.setText("Ready when you are.")
            self.notify(f"Couldn't look up {place}: {message}", "error", 8000)

        self.start_button.setEnabled(False)
        self.status.setText(f"Finding {place} on the map...")
        Task(locate).start(on_result=self.guard(found), on_error=self.guard(failed),
                           on_done=self.guard(lambda: self.start_button.setEnabled(True)))

    def run(self, search_id: int) -> None:
        """Start (or resume) a saved search."""
        from app.workers.scrape import ScrapeWorker

        if self.worker is not None:
            return
        self.search_id = search_id
        leads_page = self.window_.page("leads")
        if leads_page is not None:  # the Leads page always shows the latest search
            leads_page.select_search(search_id)
        record = searches.get(search_id)
        self.total_queries = len(searches.build_queries(record["options"]))
        self.counts = {"leads": 0, "email": 0, "phone": 0}
        self.known: dict[str, dict] = {}  # what each lead added to the tiles, to undo on removal
        self.queries_done = len(record["progress"].get("done", []))
        self.tile_web.update_value("-")
        self.tile_ai.update_value("-")
        self.tile_ai.setVisible(bool(record["options"]["smart"]))
        for lead in searches.leads(search_id):
            self._count(lead)
        self._show_counts()

        self.worker = ScrapeWorker(search_id)
        self.worker.signals.leads.connect(self._on_leads)
        self.worker.signals.updated.connect(self._on_updated)
        self.worker.signals.removed.connect(self._on_removed)
        self.worker.signals.checked.connect(self._on_checked)
        self.worker.signals.scored.connect(
            lambda done, total: self.tile_ai.update_value(f"{done:,} of {total:,}"))
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
        elif result.get("ai_error"):
            self.status.setText("Smart mode stopped: " + result["ai_error"])
            self.notify(f"Smart mode stopped: {result['ai_error']} Leads found so far are "
                        "saved; fix it on the Smart mode page, then resume from Past searches.",
                        "warn", 10000)
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
