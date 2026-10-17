"""New search: what to look for, where, which businesses, and the run itself."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QSpinBox, QWidget

from app.core import db, enrich, geo, hours, scraper
from app.core import search as searches
from app.ui.pages.base import Page
from app.core.places import FIELD_GROUPS, HEADERS
from app.ui.widgets.common import (Card, small_button, ChoiceButtons, FormRow, ProgressRow, Section, StatTile,
                                   confirm_button, danger_button, flow_row, hint, muted, row,
                                   secondary_button, select_button)
from app.ui.widgets.checklist import CheckList
from app.ui.widgets.inputs import checkbox, combo, line_edit
from app.ui.widgets.type_picker import TypePicker
from app.workers.base import Task

# Filled in only by visiting the business's website
FROM_WEBSITE = {"emails", "facebook", "instagram", "linkedin", "twitter", "youtube", "tiktok",
                "company_age", "domain_created", "age_source", "owner_name", "owner_source",
                "owner_linkedin"}
TIMES = [f"{hour:02d}:{minute:02d}" for hour in range(24) for minute in (0, 30)]
RATINGS = [("3.5", "3.5"), ("4", "4"), ("4.5", "4.5")]
STEPS = {1: "Searching Google", 2: "Checking websites", 3: "Picking the best leads"}
MORE_CITIES = 10


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
                       "Pick business types from the list, or type them the way you would into "
                       "Google Maps. Separate several with commas.")
        self.niches = TypePicker("Click to pick, or type: dentist, real estate agency, "
                                 "coffee shop...")
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
                          "founded, so businesses without a website only appear under Any age. "
                          "Websites whose age can't be found are kept, marked Unknown, and "
                          "ranked after the rest.")
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
                ("Stop after", self.max_results, "The best this many, shared fairly between "
                                                 "your cities and business types")):
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
        self.require_address = checkbox("Must show its address (some businesses hide it on "
                                        "Google)", last["require_address"])
        self.skip_closed = checkbox("Leave out closed businesses", last["skip_closed"])
        self.skip_known = checkbox("Leave out businesses I found in earlier searches",
                                   last["skip_known"])
        for box in (self.require_phone, self.require_address, self.skip_closed,
                    self.skip_known):
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
                          "Highlighted details are included; click one to leave it out (it "
                          "greys out) or put it back. Left-out details are not in the Leads "
                          "table or the Excel file. Name is always included.")
        self.detail_boxes: dict[str, object] = {}
        for group, keys in FIELD_GROUPS:
            container, flow = flow_row(spacing=14)
            for key in keys:
                box = select_button(HEADERS[key], key in last["fields"] or key == "name")
                self.detail_boxes[key] = box
                flow.addWidget(box)
            group_row = FormRow(group)
            group_row.add(container)
            details.add(group_row)
        self.detail_boxes["name"].setEnabled(False)
        details.add(row(hint("Emails, social media, company age and the owner need \"Visit "
                             "each website\" switched on above."),
                        small_button("Select all", lambda: self._tick_details(True)),
                        small_button("Select none", lambda: self._tick_details(False)),
                        stretch=0))
        layout.addWidget(details)
        self.find_emails.toggled.connect(self._website_details)
        self._website_details(self.find_emails.isChecked())
        layout.addStretch(1)

        # --- run bar (stays visible below the scrolling form) ---------------
        bar = Card(padding=14)
        stats = QHBoxLayout()
        stats.setSpacing(10)
        self.tile_found = StatTile("Businesses found", "0")
        self.tile_places = StatTile("Searches done", "0")
        self.tile_web = StatTile("Websites checked", "-")
        self.tile_email = StatTile("With an email", "-")
        self.tile_phone = StatTile("With a phone", "0")
        self.tile_ai = StatTile("AI checked", "-")
        self.tile_best = StatTile("Best leads", "-")
        for tile in (self.tile_found, self.tile_places, self.tile_web, self.tile_email,
                     self.tile_phone, self.tile_ai, self.tile_best):
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
        # When a search comes up short: why, and ways to widen it
        self.summary = hint("")
        self.summary.hide()
        bar.add(self.summary)
        self.more_cities_button = secondary_button(f"Add {MORE_CITIES} more cities",
                                                   self._add_cities)
        self.any_age_button = secondary_button("Allow any company age", self._any_age)
        self.widen = row(self.more_cities_button, self.any_age_button, None)
        self.widen.hide()
        bar.add(self.widen)
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
            "require_address": self.require_address.isChecked(),
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
        for name in ("require_phone", "require_address", "skip_closed", "skip_known", "find_emails", "find_owner",
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
        self.title = record["title"]
        limit = int(record["options"]["max_results"] or 0)
        self.step = 0
        for tile in (self.tile_web, self.tile_email, self.tile_ai):
            tile.update_value("-")
        self.tile_best.update_value(f"- of {limit:,}" if limit else "-")
        self.tile_ai.setVisible(bool(record["options"]["smart"]))

        self.worker = ScrapeWorker(search_id)
        self.worker.signals.step.connect(self._on_step)
        self.worker.signals.found.connect(self._on_found)
        self.worker.signals.checked.connect(self._on_checked)
        self.worker.signals.scored.connect(self._on_scored)
        self.worker.signals.progress.connect(self._on_progress)
        self.worker.signals.message.connect(lambda text, level: self.notify(text, level))
        self.worker.signals.finished.connect(self._on_finished)
        self.worker.signals.failed.connect(self._on_failed)
        self._set_running(True)
        self.status.setText(f"Starting: {self.title}")
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
        self.summary.hide()
        self.widen.hide()
        self.stats.show()
        self.progress.setVisible(running)
        if running:
            self.progress.set_busy()
        self.window_.set_status(left="Searching..." if running else "")

    # Each step drives the bar while it runs; the tiles only ever count up
    def _on_step(self, step: int) -> None:
        self.step = step
        self.progress.set_busy()
        self.status.setText(f"Step {step} of 3: {STEPS[step]}"
                            + (f" for {self.title}" if step == 1 else ""))

    def _on_found(self, fits: int, phones: int) -> None:
        self.tile_found.update_value(f"{fits:,}")
        self.tile_phone.update_value(f"{phones:,}")

    def _on_progress(self, done: int, total: int, _detail: str) -> None:
        self.tile_places.update_value(f"{done:,} of {total:,}")
        if self.step == 1:
            self.progress.set_progress(done, total)

    def _on_checked(self, done: int, total: int, emails: int) -> None:
        self.tile_web.update_value(f"{done:,} of {total:,}")
        self.tile_email.update_value(f"{emails:,}")
        if self.step == 2:
            self.progress.set_progress(done, total)

    def _on_scored(self, done: int, total: int) -> None:
        self.tile_ai.update_value(f"{done:,} of {total:,}")
        if self.step == 3:
            self.progress.set_progress(done, total)

    def _on_finished(self, result: dict) -> None:
        self.worker = None
        self._set_running(False)
        found, wanted = result["found"], result["wanted"]
        self.tile_best.update_value(f"{found:,} of {wanted:,}" if wanted else f"{found:,}")
        leads_page = self.window_.page("leads")
        if leads_page is not None:
            leads_page.select_search(self.search_id)
        if result["blocked"]:
            self.status.setText(f"Paused: Google is limiting requests. The best {found:,} so "
                                "far are in Leads.")
            self.notify("Google asked GeoHarvest to slow down. Everything found so far is saved. "
                        "Wait about 15 minutes, then resume it from Past searches.", "warn", 10000)
        elif result.get("ai_error"):
            self.status.setText("Smart mode stopped: " + result["ai_error"])
            self.notify(f"Smart mode stopped: {result['ai_error']} Leads found so far are "
                        "saved; fix it on the Smart mode page, then resume from Past searches.",
                        "warn", 10000)
        elif result["status"] == "done":
            self.status.setText(f"Done: the best {found:,} of {result['listed']:,} businesses "
                                "Google listed.")
            if wanted and found < wanted:
                self._explain_shortfall(result)
            else:
                self.notify(f"Search finished: {found:,} leads.", "success")
        else:
            self.status.setText(f"Stopped. The best {found:,} so far are in Leads; resume it "
                                "from Past searches.")
        self.window_.search_finished.emit(self.search_id)
        self.window_.refresh_status()

    def _explain_shortfall(self, result: dict) -> None:
        """Why the places chosen did not have enough, and the ways to widen the search."""
        reasons = ", ".join(f"{count:,} {reason}" for reason, count in
                            list(result["dropped"].items())[:5])
        self.summary.setText(
            f"Only {result['found']:,} of the {result['wanted']:,} leads you asked for: Google "
            f"listed {result['listed']:,} businesses in these places"
            + (f", and left out were: {reasons}." if reasons else ".")
            + " Widen the search below; it carries on from where it is.")
        options = searches.get(self.search_id)["options"]
        self.more_cities_button.setVisible(bool(self._spare_cities(options)))
        self.any_age_button.setVisible(options["company_age"] != "any" and any(
            reason in result["dropped"] for reason in enrich.AGE_REASONS))
        self.summary.show()
        self.widen.setVisible(self.more_cities_button.isVisibleTo(self.widen)
                              or self.any_age_button.isVisibleTo(self.widen))
        self.notify(f"Search finished with {result['found']:,} of {result['wanted']:,} leads. "
                    "See why below.", "warn", 6000)

    @staticmethod
    def _spare_cities(options: dict) -> list[str]:
        """The next-biggest cities not searched yet, taking turns between the countries."""
        if options["where"] != "cities":
            return []
        chosen = set(searches.places_for(options))
        ranked = sorted((rank, f"{city}, {country}") for country in geo.expand(options["countries"])
                        for rank, city in enumerate(geo.cities(country)))
        return [key for _rank, key in ranked if key not in chosen][:MORE_CITIES]

    def _widen(self, change) -> None:
        options = searches.get(self.search_id)["options"]
        change(options)
        searches.set_options(self.search_id, options)
        self.load_options(options)
        self.run(self.search_id)

    def _add_cities(self) -> None:
        self._widen(lambda options: options.update(
            cities=searches.places_for(options) + self._spare_cities(options)))

    def _any_age(self) -> None:
        searches.undrop(self.search_id, enrich.AGE_REASONS)
        self._widen(lambda options: options.update(company_age="any"))

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
