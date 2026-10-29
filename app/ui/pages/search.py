"""New search: what to look for, where, which businesses, and the run itself."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QInputDialog, QMenu, QSpinBox, QVBoxLayout, QWidget

from app.core import db, geo, hours, scraper
from app.core import search as searches
from app.i18n import t
from app.ui.pages.base import Page
from app.core.places import FIELD_GROUPS, HEADERS, RECORD_FIELDS
from app.ui.widgets.common import (Card, Columns, small_button, ChoiceButtons, FormRow, ProgressRow, Section, StatTile,
                                   confirm_button, danger_button, flow_row, hint, muted, row,
                                   secondary_button, select_button, clear_layout, wrap_row)
from app.ui.widgets.dialogs import ConfirmDialog
from app.ui.widgets.checklist import CheckList
from app.ui.widgets.inputs import combo, line_edit
from app.ui.widgets.range_slider import RangeSlider
from app.ui.widgets.type_picker import TypePicker
from app.workers.base import Task

# Filled in only by visiting the business's website
FROM_WEBSITE = {"emails", "facebook", "instagram", "linkedin", "twitter", "youtube", "tiktok",
                "company_age", "domain_created", "age_source", "owner_name", "owner_source",
                "owner_linkedin"}
TIMES = [f"{hour:02d}:{minute:02d}" for hour in range(24) for minute in (0, 30)]
STEPS = {1: "Searching Google", 2: "Checking websites", 3: "Ranking the leads"}
MORE_CITIES = 10
# Slider steps: finer where people choose (ratings near 4-5, small review counts)
RATING_STEPS = [0, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5] + [round(3.6 + i / 10, 1) for i in range(15)]
NO_MAX = 10 ** 9
REVIEW_STEPS = [0, 1, 2, 3, 5, 10, 15, 20, 25, 30, 40, 50, 75, 100, 150, 200, 300, 500, 750,
                1000, 2000, 5000, 10000, NO_MAX]
AGE_STEPS = list(range(31))  # the last one means "30 years or more"
# Options that are a select button of the same name on the form
REQUIREMENT_BUTTONS = ("require_phone", "require_address", "require_email", "require_social",
                       "require_linkedin", "require_owner", "require_claimed", "require_hours",
                       "skip_closed", "skip_known", "open_now", "open_24h", "open_weekends",
                       "open_at", "find_emails", "find_owner")


def rating_label(value: float) -> str:
    return t("Any") if not value else f"{value:.1f}"


def reviews_label(value: int) -> str:
    return t("No maximum") if value == NO_MAX else f"{value:,}"


def age_label(value: int) -> str:
    return t("{years}+ years", years=value) if value == AGE_STEPS[-1] else \
        t("{years} years", years=value) if value != 1 else t("1 year")


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
        self.countries.set_items([(r, t("{r} (all its countries)", r=r)) for r in geo.REGIONS]
                                 + [(c, c) for c in geo.countries()], set())
        self.cities = CheckList("Search cities")
        self.extra_places: list[str] = []
        self.extra_place = line_edit("A town or area that is not listed")
        self.extra_place.returnPressed.connect(self._add_place)
        left, right = FormRow("Countries"), FormRow("Cities")
        left.add(self.countries)
        right.add(self.cities)
        right.add(row(self.extra_place, small_button("Add", self._add_place), stretch=0))
        self.cities_box = Columns(left, right, stack_below=720)
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

        # --- requirements ---------------------------------------------------
        which = Section("Requirements",
                        "Click a requirement to switch it on (highlighted) or off (greyed out). "
                        "Only businesses that meet every one you switch on become leads.")
        self.use_case_row = FormRow("Quick setup", "Sets the requirements below for a common "
                                                   "job, or to one of your own presets. Change "
                                                   "anything afterwards.")
        self.quick_holder = QWidget()
        self.quick_holder.setProperty("role", "plain")
        QVBoxLayout(self.quick_holder).setContentsMargins(0, 0, 0, 0)
        self.use_case_row.add(self.quick_holder)
        self._fill_quick_setup()
        which.add(self.use_case_row)

        age_row = FormRow("Company age",
                          "Estimated from when the business's website was registered (or first "
                          "appeared online, for countries whose registry keeps that private, "
                          "which takes longer). Businesses without a website only appear with "
                          "any age. Websites whose age can't be found are kept, marked Unknown, "
                          "and ranked after the rest.")
        self.age_quick = ChoiceButtons(
            [("any", "Any age"), ("startup", "Startups (under 3 years)"),
             ("established", "Established (3 years or more)"), ("own", "My own range")], "any",
            on_change=self._age_quick_changed)
        self.age = RangeSlider(AGE_STEPS, 0, AGE_STEPS[-1], age_label)
        self.age.changed.connect(lambda *_values: self._age_moved())
        age_row.add(self.age_quick)
        age_row.add(self.age)
        which.add(age_row)

        self.rating = RangeSlider(RATING_STEPS, 0, 5.0, rating_label)
        self.reviews = RangeSlider(REVIEW_STEPS, 0, NO_MAX, reviews_label)
        fields = []
        for label, note, slider in (
                ("Google rating", "Drag either end. Any includes businesses with no rating yet.",
                 self.rating),
                ("Number of reviews", "Few reviews often means a business that needs more "
                                      "customers.", self.reviews)):
            field = FormRow(label, note)
            field.add(slider)
            fields.append(field)
        which.add(Columns(*fields, stack_below=640, spacing=32))

        self.min_leads = spin(0, 100000, int(last["min_leads"]), " leads", "Everything found")
        self.min_leads.setFixedWidth(200)
        count_row = FormRow("Minimum leads", "GeoHarvest keeps searching until at least this "
                                             "many businesses meet your requirements, digging "
                                             "deeper into each city if it has to. Every match "
                                             "it finds on the way is kept, best first.")
        count_row.add(self.min_leads)
        which.add(count_row)

        website_row = FormRow("Website", "\"No website\" finds businesses you could build a "
                                         "site for. Emails, social media, company age and the "
                                         "owner's name come from websites, so those stay empty.")
        self.website = ChoiceButtons([("any", "Any"), ("yes", "Has a website"),
                                      ("no", "No website")], last["website"])
        website_row.add(self.website)
        which.add(website_row)

        self.require_phone = select_button("Phone number", last["require_phone"])
        self.require_address = select_button("Address shown on Google", last["require_address"])
        self.require_email = select_button("Email", last["require_email"])
        self.require_social = select_button("Social media", last["require_social"])
        self.require_linkedin = select_button("LinkedIn", last["require_linkedin"])
        self.require_owner = select_button("Owner's name", last["require_owner"])
        self.require_claimed = select_button("Claimed by owner", last["require_claimed"])
        self.require_hours = select_button("Opening hours listed", last["require_hours"])
        must_row = FormRow("Must have", "Email, social media, LinkedIn and the owner come from "
                                        "the business's website, so they switch on \"Visit each "
                                        "website\" below, and the search keeps going until "
                                        "enough have them.")
        container, flow = flow_row(spacing=10)
        for box in (self.require_phone, self.require_address, self.require_email,
                    self.require_social, self.require_linkedin, self.require_owner,
                    self.require_claimed, self.require_hours):
            flow.addWidget(box)
        must_row.add(container)
        which.add(must_row)

        self.skip_closed = select_button("Closed businesses", last["skip_closed"])
        self.skip_known = select_button("Businesses I found in earlier searches",
                                        last["skip_known"])
        leave_row = FormRow("Leave out")
        container, flow = flow_row(spacing=10)
        flow.addWidget(self.skip_closed)
        flow.addWidget(self.skip_known)
        leave_row.add(container)
        which.add(leave_row)

        hours_row = FormRow("Open", "In each business's own time zone. Businesses that don't "
                                    "list their hours on Google are left out while any of these "
                                    "is on.")
        self.open_now = select_button("Now", last["open_now"])
        self.open_24h = select_button("24 hours", last["open_24h"])
        self.open_weekends = select_button("On weekends", last["open_weekends"])
        self.open_at = select_button("On", last["open_at"])
        self.open_day = combo(hours.DAYS, hours.DAYS[int(last["open_day"])], translate=False)
        self.open_time = combo(TIMES, last["open_time"], translate=False)
        container, flow = flow_row(spacing=10)
        for box in (self.open_now, self.open_24h, self.open_weekends,
                    row(self.open_at, self.open_day, muted("at", wrap=False), self.open_time)):
            flow.addWidget(box)
        hours_row.add(container)
        which.add(hours_row)
        layout.addWidget(which)

        # --- extra ----------------------------------------------------------
        extra = Section("Extra detail", "Click to switch on (highlighted) or off (greyed out).")
        self.find_emails = select_button("Visit each website", last["find_emails"])
        self.find_owner = select_button("Look for the owner", last["find_owner"])
        self.smart = select_button("Smart mode", last["smart"])
        container, flow = flow_row(spacing=10)
        for box in (self.find_emails, self.find_owner, self.smart):
            flow.addWidget(box)
        extra.add(container)
        extra.add(hint("Visit each website: emails, social media (Facebook, Instagram, "
                       "LinkedIn...) and company age. Look for the owner: their name (on the "
                       "website or in the domain record) and their LinkedIn profile, if the "
                       "website links it. Smart mode: AI checks every lead against your ideal "
                       "customer."))
        self.smart_note = hint("")
        extra.add(self.smart_note)
        layout.addWidget(extra)
        # A requirement only a website can answer switches the visit on; switching the
        # visit off switches those requirements off
        for box in (self.require_email, self.require_social, self.require_linkedin):
            box.toggled.connect(lambda on: on and self.find_emails.setChecked(True))
        self.require_owner.toggled.connect(lambda on: on and self.find_owner.setChecked(True))
        self.find_owner.toggled.connect(lambda on: on and self.find_emails.setChecked(True))
        self.find_owner.toggled.connect(lambda on: on or self.require_owner.setChecked(False))

        # --- details ----------------------------------------------------------
        details = Section("Details to include",
                          "Highlighted details are included; click one to leave it out (it "
                          "greys out) or put it back. Left-out details are not in the Leads "
                          "table or the Excel file. With none picked, Name is included.")
        self.detail_boxes: dict[str, object] = {}
        for group, keys in FIELD_GROUPS:
            if keys is RECORD_FIELDS:
                continue  # dates GeoHarvest keeps; picked under Leads > Columns
            container, flow = flow_row(spacing=14)
            for key in keys:
                box = select_button(HEADERS[key], key in last["fields"])
                self.detail_boxes[key] = box
                flow.addWidget(box)
            group_row = FormRow(group)
            group_row.add(container)
            details.add(group_row)
        details.add(row(hint("Emails, social media, company age and the owner need \"Visit "
                             "each website\" switched on above."),
                        small_button("Select all", lambda: self._tick_details(True)),
                        small_button("Select none", lambda: self._tick_details(False)),
                        stretch=0))
        layout.addWidget(details)
        self.find_emails.toggled.connect(self._website_details)
        self.find_emails.toggled.connect(lambda _on: self._update_plan())
        self.min_leads.valueChanged.connect(lambda _value: self._update_plan())
        self._website_details(self.find_emails.isChecked())
        layout.addStretch(1)

        # --- run bar (stays visible below the scrolling form) ---------------
        bar = Card(padding=14)
        self.stats, stats = flow_row(spacing=10)  # tiles wrap in a narrow window
        self.tile_found = StatTile("Businesses found", "0")
        self.tile_places = StatTile("Searches done", "0")
        self.tile_web = StatTile("Websites checked", "-")
        self.tile_email = StatTile("With an email", "-")
        self.tile_phone = StatTile("With a phone", "0")
        self.tile_ai = StatTile("AI checked", "-")
        self.tile_best = StatTile("Leads", "-")
        for tile in (self.tile_found, self.tile_places, self.tile_web, self.tile_email,
                     self.tile_phone, self.tile_ai, self.tile_best):
            stats.addWidget(tile)
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
        self.more_cities_button = secondary_button(t("Add {more_cities} more cities",
                                                     more_cities=MORE_CITIES),
                                                   self._add_cities)
        self.related_button = secondary_button("Add related business types", self._add_related)
        self.any_age_button = secondary_button("Allow any company age", self._any_age)
        self.widen = row(self.more_cities_button, self.related_button, self.any_age_button, None)
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
            text = (t("{count:,} searches (the area is covered in small map views, one "
                      "search per view and business type).", count=count))
        else:
            count = len(searches.build_queries({
                "niches": niches, "countries": self._chosen_countries(),
                "cities": self.cities.checked()})) if self.cities.checked() else 0
            countries, cities = len(self._chosen_countries()), len(self.cities.checked())
            text = t("Countries: {countries}, cities: {cities:,}. {count:,} searches (one per "
                     "city and business type).", countries=countries, cities=cities, count=count)
        self.plan.setText(f"{text} {self._estimate(count)}" if count else "")

    def _estimate(self, count: int) -> str:
        """The live estimate under the places: a rough guide to size and time."""
        if not hasattr(self, "find_emails"):  # still building the form
            return ""
        visits = self.find_emails.isChecked()
        listed, low, high = searches.estimate(count, int(db.get_setting("parallel_searches", 4)),
                                              visits)
        span = t("about {low} minutes", low=low) if low == high else \
            t("{low} to {high} minutes", low=low, high=high)
        text = t("Rough estimate: up to {listed:,} businesses, {span}", listed=listed, span=span)
        text += t(" with the website visits.") if visits else "."
        if self.min_leads.value():
            text += " " + t("Asking for a minimum can make it search deeper and take longer.")
        return text

    def _tick_details(self, on: bool) -> None:
        for box in self.detail_boxes.values():
            box.setChecked(on)

    def _website_details(self, on: bool) -> None:
        for key in FROM_WEBSITE:
            self.detail_boxes[key].setEnabled(on)
        if not on:
            for box in (self.find_owner, self.require_email, self.require_social,
                        self.require_linkedin, self.require_owner):
                box.setChecked(False)

    def _age_quick_changed(self, key: str) -> None:
        if key in searches.AGE_PRESETS:
            low, high = searches.AGE_PRESETS[key]
            self.age.set(low, AGE_STEPS[-1] if high < 0 else high)

    def _age_moved(self) -> None:
        """The quick button that matches the slider lights up, else "My own range"."""
        low, high = self.age.get()
        chosen = (low, -1 if high == AGE_STEPS[-1] else high)
        self.age_quick.set(next((key for key, value in searches.AGE_PRESETS.items()
                                 if value == chosen), "own"))

    def _age_range(self) -> tuple[int, int]:
        low, high = self.age.get()
        return low, -1 if high == AGE_STEPS[-1] else high

    def _set_age(self, low: int, high: int) -> None:
        self.age.set(low, AGE_STEPS[-1] if high < 0 else high)
        self._age_moved()

    def _use_case(self, key: str) -> None:
        """Quick setup: put the requirements for a common job on the form."""
        self.load_options({**self.options(), **searches.USE_CASES[key]})
        self.notify(t("Requirements set for {job}. Change anything you like.",
                      job=t(dict(searches.USE_CASE_NAMES)[key]).lower()), "success")

    # --- presets -------------------------------------------------------------
    def _fill_quick_setup(self) -> None:
        layout = self.quick_holder.layout()
        clear_layout(layout)
        buttons = [small_button(label, lambda _c=False, k=key: self._use_case(k))
                   for key, label in searches.USE_CASE_NAMES]
        for name in searches.presets():
            button = small_button(name, lambda _c=False, n=name: self._use_preset(n))
            button.setToolTip(t("Your preset. Right-click to delete it."))
            button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            button.customContextMenuRequested.connect(
                lambda _pos, n=name, b=button: self._preset_menu(n, b))
            buttons.append(button)
        save = small_button("Save as a preset...", self._save_preset)
        save.setToolTip(t("Keep everything on this form except the business types and places, "
                          "to use again with one click"))
        layout.addWidget(wrap_row(*buttons, save))

    def _use_preset(self, name: str) -> None:
        preset = searches.presets().get(name)
        if preset is None:
            return
        self.load_options({**self.options(), **preset})
        self.notify(t("Requirements set from your preset {name}.", name=name), "success")

    def _save_preset(self) -> None:
        name, ok = QInputDialog.getText(
            self, t("Save as a preset"),
            t("A name for these requirements and details. The business types and places "
              "aren't saved, so the preset works for any search."))
        name = " ".join(name.split())[:40]
        if not ok or not name:
            return
        if name in searches.presets() and not ConfirmDialog.ask(
                self, "Replace the preset?",
                t("You already have a preset called {name}. Replace it?", name=name), "Replace"):
            return
        searches.save_preset(name, self.options())
        self._fill_quick_setup()
        self.notify(t("Saved the preset {name}. It is under Quick setup.", name=name), "success")

    def _preset_menu(self, name: str, button) -> None:
        menu = QMenu(self)
        menu.addAction(t("Use it"), lambda: self._use_preset(name))
        menu.addAction(t("Delete this preset"), lambda: self._delete_preset(name))
        menu.exec(button.mapToGlobal(button.rect().bottomLeft()))

    def _delete_preset(self, name: str) -> None:
        if ConfirmDialog.ask(self, "Delete this preset?",
                             t("Delete {name}? Searches you ran with it are not affected.",
                               name=name), "Delete", danger=True):
            searches.delete_preset(name)
            self._fill_quick_setup()

    def on_show(self) -> None:
        ready = bool(db.get_setting("ai_provider", ""))
        self.smart.setEnabled(ready)
        if not ready:
            self.smart.setChecked(False)
        self.smart_note.setText("" if ready else
                                t("Set up Smart mode first: open Smart mode in the menu and add a "
                                "free AI key or a local model."))

    def options(self) -> dict:
        place = self.area_place.text().strip()
        found = self.located if self.located and self.located[0] == place else None
        min_rating, max_rating = self.rating.get()
        min_reviews, max_reviews = self.reviews.get()
        age_min, age_max = self._age_range()
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
            "age_min": age_min,
            "age_max": age_max,
            "min_rating": float(min_rating),
            "max_rating": 0.0 if max_rating >= 5 else float(max_rating),
            "min_reviews": min_reviews,
            "max_reviews": -1 if max_reviews == NO_MAX else max_reviews,
            "min_leads": self.min_leads.value(),
            "website": self.website.get(),
            **{name: getattr(self, name).isChecked() for name in REQUIREMENT_BUTTONS},
            "open_day": hours.DAYS.index(self.open_day.currentText()),
            "open_time": self.open_time.currentText(),
            "smart": self.smart.isChecked(),
            # nothing picked still shows who the business is
            "fields": [key for key, box in self.detail_boxes.items() if box.isChecked()]
                      or ["name"],
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
        self._set_age(int(options["age_min"]), int(options["age_max"]))
        self.rating.set(float(options["min_rating"]), float(options["max_rating"] or 5.0))
        self.reviews.set(int(options["min_reviews"]),
                         NO_MAX if int(options["max_reviews"]) < 0 else int(options["max_reviews"]))
        self.min_leads.setValue(int(options["min_leads"]))
        self.website.set(options["website"])
        # The website visit first: switching it off would clear the requirements that need it
        for name in ("find_emails", "find_owner", *REQUIREMENT_BUTTONS):
            getattr(self, name).setChecked(bool(options[name]))
        self.open_day.setCurrentText(hours.DAYS[int(options["open_day"])])
        self.open_time.setCurrentText(options["open_time"])
        for key, box in self.detail_boxes.items():
            box.setChecked(key in options["fields"])
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
        if options["website"] == "no" and searches.age_filtered(options):
            return "Company age comes from the website, so it can't be used with \"No website\"."
        if options["website"] == "no" and any(options[key] for key in searches.FROM_WEBSITE_REQUIREMENTS):
            return ("Emails, social media, LinkedIn and the owner come from the website, so "
                    "they can't be required with \"No website\".")
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
                self.status.setText(t("Ready when you are."))
                self.notify(t("Google Maps couldn't find \"{place}\". Try adding the city or "
                              "country.", place=place), "warn", 6000)
                return
            self.located = (place, *point)
            self.start()

        def failed(message: str) -> None:
            self.status.setText(t("Ready when you are."))
            self.notify(t("Couldn't look up {place}: {message}",
                          place=place, message=message), "error", 8000)

        self.start_button.setEnabled(False)
        self.status.setText(t("Finding {place} on the map...", place=place))
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
        limit = int(record["options"]["min_leads"] or 0)
        self.step = 0
        for tile in (self.tile_web, self.tile_email, self.tile_ai):
            tile.update_value("-")
        self.limit = limit
        self.tile_best.update_value(t("- of {limit:,}", limit=limit) if limit else "-")
        self.tile_ai.setVisible(bool(record["options"]["smart"]))

        self.worker = ScrapeWorker(search_id)
        self.worker.signals.step.connect(self._on_step)
        self.worker.signals.found.connect(self._on_found)
        self.worker.signals.checked.connect(self._on_checked)
        self.worker.signals.scored.connect(self._on_scored)
        self.worker.signals.leads.connect(self._on_leads)
        self.worker.signals.progress.connect(self._on_progress)
        self.worker.signals.message.connect(lambda text, level: self.notify(text, level))
        self.worker.signals.finished.connect(self._on_finished)
        self.worker.signals.failed.connect(self._on_failed)
        self._set_running(True)
        self.status.setText(t("Starting: {title}", title=self.title))
        self.worker.start()

    def stop(self) -> None:
        if self.worker is not None:
            self.worker.stop()
            self.stop_button.setEnabled(False)
            self.stop_button.setText(t("Stopping..."))

    def _set_running(self, running: bool) -> None:
        self.start_button.setVisible(not running)
        self.stop_button.setVisible(running)
        self.stop_button.setEnabled(True)
        self.stop_button.setText(t("Stop"))
        self.open_button.setVisible(True)
        self.summary.hide()
        self.widen.hide()
        self.stats.show()
        self.progress.setVisible(running)
        if running:
            self.progress.set_busy()
        self.window_.set_status(left=t("Searching...") if running else "")

    # Each step drives the bar while it runs; the tiles only ever count up
    def _on_step(self, step: int) -> None:
        self.step = step
        self.progress.set_busy()
        self.status.setText(t("Step {step} of 3: {doing} for {title}", step=step,
                              doing=STEPS[step], title=self.title) if step == 1 else
                            t("Step {step} of 3: {doing}", step=step, doing=STEPS[step]))

    def _on_found(self, fits: int, phones: int) -> None:
        self.tile_found.update_value(f"{fits:,}")
        self.tile_phone.update_value(f"{phones:,}")

    def _on_progress(self, done: int, total: int, _detail: str) -> None:
        self.tile_places.update_value(t("{done:,} of {total:,}", done=done, total=total))
        if self.step == 1:
            self.progress.set_progress(done, total)

    def _on_checked(self, done: int, total: int, emails: int) -> None:
        self.tile_web.update_value(t("{done:,} of {total:,}", done=done, total=total))
        self.tile_email.update_value(f"{emails:,}")
        if self.step == 2:
            self.progress.set_progress(done, total)

    def _on_scored(self, done: int, total: int) -> None:
        self.tile_ai.update_value(t("{done:,} of {total:,}", done=done, total=total))
        if self.step == 3:
            self.progress.set_progress(done, total)

    def _on_leads(self, count: int) -> None:
        self.tile_best.update_value(t("{count:,} of {limit:,}",
                                      count=count,
                                      limit=self.limit) if self.limit else f"{count:,}")

    def _on_finished(self, result: dict) -> None:
        self.worker = None
        self._set_running(False)
        found, wanted = result["found"], result["wanted"]
        self.tile_best.update_value(t("{found:,} of {wanted:,}",
                                      found=found, wanted=wanted) if wanted else f"{found:,}")
        leads_page = self.window_.page("leads")
        if leads_page is not None:
            leads_page.select_search(self.search_id)
        if result["blocked"] or result.get("ai_error") or result["status"] == "done":
            self.window_.tell_user(t("Search finished") if result["status"] == "done" else
                                   t("Search paused"),
                                   t("{found:,} leads for {title}.", found=found,
                                     title=searches.title(searches.get(self.search_id)["options"])))
        if result["blocked"]:
            self.status.setText(t("Paused: Google is limiting requests. The {found:,} leads "
                                  "so far are in Leads.", found=found))
            self.notify("Google asked GeoHarvest to slow down. Everything found so far is saved. "
                        "Wait about 15 minutes, then resume it from Past searches.", "warn", 10000)
        elif result.get("ai_error"):
            self.status.setText(t("Smart mode stopped: {error}", error=result["ai_error"]))
            self.notify(t("Smart mode stopped: {ai_error} Leads found so far are saved; fix "
                          "it on the Smart mode page, then resume from Past searches.",
                          ai_error=result['ai_error']),
                        "warn", 10000)
        elif result["status"] == "done":
            self.status.setText(t("Done: {found:,} leads meet your requirements, out of "
                                  "{listed:,} businesses Google listed.",
                                  found=found, listed=result['listed']))
            if wanted and found < wanted:
                self._explain_shortfall(result)
            else:
                self.notify(t("Search finished: {found:,} leads.", found=found), "success")
        else:
            self.status.setText(t("Stopped. The {found:,} leads so far are in Leads; resume "
                                  "it from Past searches.", found=found))
        self.window_.search_finished.emit(self.search_id)
        self.window_.refresh_status()

    def _explain_shortfall(self, result: dict) -> None:
        """Why the places chosen did not have enough, and the ways to widen the search."""
        reasons = ", ".join(f"{count:,} {reason}" for reason, count in
                            list(result["dropped"].items())[:5])
        self.summary.setText(
            t("Only {found:,} of the {wanted:,} leads you asked for, after searching deeper "
              "inside every city: Google listed {listed:,} businesses in these places",
              found=result['found'], wanted=result['wanted'], listed=result['listed'])
            + (t(", and left out were: {reasons}.", reasons=reasons) if reasons else ".")
            + " " + t("Widen the search below; it carries on from where it is."))
        options = searches.get(self.search_id)["options"]
        self.more_cities_button.setVisible(bool(self._spare_cities(options)))
        self.related_button.setVisible(bool(searches.related_types(options["niches"])))
        self.any_age_button.setVisible(searches.age_filtered(options) and any(
            searches.is_age_reason(reason) for reason in result["dropped"]))
        self.summary.show()
        self.widen.setVisible(any(button.isVisibleTo(self.widen) for button in (
            self.more_cities_button, self.related_button, self.any_age_button)))
        self.notify(t("Search finished with {found:,} of {wanted:,} leads. See why below.",
                      found=result['found'], wanted=result['wanted']), "warn", 6000)

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

    def _add_related(self) -> None:
        self._widen(lambda options: options.update(
            niches=options["niches"] + searches.related_types(options["niches"])))

    def _any_age(self) -> None:
        searches.undrop(self.search_id, tuple(
            reason for reason in searches.dropped_counts(self.search_id)
            if searches.is_age_reason(reason)))
        self._widen(lambda options: options.update(age_min=0, age_max=-1))

    def _on_failed(self, message: str) -> None:
        self.worker = None
        self._set_running(False)
        if self.search_id is not None:
            searches.set_status(self.search_id, "stopped")
        self.status.setText(t("The search stopped because of an error."))
        self.notify(t("The search stopped: {message}", message=message), "error", 8000)

    def open_leads(self) -> None:
        self.window_.show_page("leads")
        page = self.window_.page("leads")
        if page is not None and self.search_id is not None:
            page.select_search(self.search_id)

    def busy_reason(self) -> str | None:
        return "a search is running" if self.worker is not None else None
