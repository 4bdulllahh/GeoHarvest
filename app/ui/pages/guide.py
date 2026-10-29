"""Start here: a checklist of the steps from a first search to leads in a spreadsheet.

Every step ticks itself from the real state of the app, so it doubles as a
progress tracker. Written for someone who has never scraped anything.
"""
from __future__ import annotations

import json

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget

from app.core import backup, db
from app.i18n import t
from app.ui import theme
from app.ui.pages.base import Page
from app.ui.widgets.common import (Card, clear_layout, hint, muted, secondary_button, set_tone,
                                   subheading)

INTRO = (
    "Welcome. GeoHarvest finds businesses on Google Maps, visits their websites for emails, "
    "owners and social media, and gives you the best ones as a list you can export. Work down "
    "the steps; each one ticks itself off once you have done it.\n\n"
    "Whatever the list is for, there is a Quick setup on the New search page: cold email "
    "(businesses with an email), cold calling (with a phone number) or building your own "
    "database (everything found, with every detail)."
)


class GuideStep(Card):
    def __init__(self, number: int, title: str, why: str, how: str, done: bool, action=None):
        super().__init__(kind="card", padding=16)
        if done:
            self.setStyleSheet(f"QFrame[role=\"card\"] {{ border-color: {theme.color('success')}; }}")

        header = QHBoxLayout()
        header.setSpacing(10)
        badge = QLabel("✓" if done else str(number))
        size = round(22 * theme.text_scale())
        badge.setFixedSize(size, size)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            f"background-color: {theme.color('success') if done else theme.color('bg_input')};"
            f"color: {'#ffffff' if done else theme.color('fg')};"
            f"border-radius: {size // 2}px; font-weight: 700;")
        header.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)
        title_label = subheading(title)
        title_label.setWordWrap(True)
        header.addWidget(title_label, 1, Qt.AlignmentFlag.AlignVCenter)
        if action:
            header.addWidget(secondary_button("Open", action, 110), 0,
                             Qt.AlignmentFlag.AlignVCenter)
        self.add_layout(header)

        body = QVBoxLayout()
        body.setContentsMargins(round(32 * theme.text_scale()), 0, 0, 0)
        body.setSpacing(2)
        body.addWidget(hint("Why it matters"))
        body.addWidget(muted(why))
        body.addSpacing(6)
        body.addWidget(hint("What to do"))
        body.addWidget(muted(how))
        self.add_layout(body)


class GuidePage(Page):
    def __init__(self, window):
        super().__init__(window)
        self.add_header("Start here")
        area = self.scroll_body().body_layout
        area.addWidget(muted(INTRO))
        self.progress_label = muted("")
        area.addWidget(self.progress_label)
        self.progress = QProgressBar()
        self.progress.setProperty("tone", "success")
        self.progress.setTextVisible(False)
        area.addWidget(self.progress)
        self.steps_holder = QWidget()
        self.steps_holder.setProperty("role", "plain")
        self.steps_layout = QVBoxLayout(self.steps_holder)
        self.steps_layout.setContentsMargins(0, 0, 0, 0)
        self.steps_layout.setSpacing(10)
        area.addWidget(self.steps_holder)
        area.addStretch(1)

    def _steps(self) -> list[dict]:
        from app.core import ai

        options = [json.loads(row["options"]) for row in db.query("SELECT options FROM searches")]
        exported = db.query_one("SELECT 1 AS x FROM leads WHERE json_extract(data, '$.exported') "
                                "IS NOT NULL LIMIT 1")
        return [
            {
                "title": "Run your first search",
                "why": "Everything starts with a type of business and the places to look. "
                       "GeoHarvest searches Google Maps city by city, so a country's ten "
                       "biggest cities already give you hundreds of businesses.",
                "how": "On New search, type a business type (dentist, real estate agency...), "
                       "pick a country and its cities, then press Start search.",
                "done": bool(options),
                "action": lambda: self.go("search"),
            },
            {
                "title": "Say what a good lead is",
                "why": "A list is only useful if you can act on it. Requirements keep only the "
                       "businesses you can actually reach: with an email for cold email, a phone "
                       "for calls, or a rating, size and age that fits what you sell.",
                "how": "Under Requirements, use a Quick setup or switch on what you need, and set "
                       "Minimum leads: GeoHarvest keeps searching deeper until it has that many. "
                       "Save it as a preset to use it again.",
                "done": any(o.get("min_leads") or o.get("website", "any") != "any" or
                            any(v for k, v in o.items() if k.startswith("require_"))
                            for o in options),
                "action": lambda: self.go("search"),
            },
            {
                "title": "Get emails, owners and social media",
                "why": "Google Maps doesn't show emails. GeoHarvest visits each business's "
                       "website to find them, along with its social media pages and, if you "
                       "ask, the owner's name and LinkedIn.",
                "how": "Keep Visit each website on under Extra detail, and switch on Look for "
                       "the owner when you want to write to a person, not a company.",
                "done": any(o.get("find_emails") for o in options),
                "action": lambda: self.go("search"),
            },
            {
                "title": "Sort, filter and export",
                "why": "Each lead gets a quality score from how much is known about the "
                       "business, and the best come first. Filtering before you export gives "
                       "you exactly the list you need.",
                "how": "On Leads, use Show (with an email, with a phone, not exported yet...) and "
                       "Sort, then Export to Excel, or More exports for HubSpot, Pipedrive, Zoho, "
                       "Salesforce and HomingPigeon.",
                "done": exported is not None,
                "action": lambda: self.go("leads"),
            },
            {
                "title": "Let an AI pick the best fits (optional)",
                "why": "Describe your ideal customer in plain words and an AI scores every lead "
                       "with a one-line reason. Free options exist; you bring the key, so "
                       "GeoHarvest stays free.",
                "how": "Open Smart mode, choose an AI (Google Gemini has a free key), describe "
                       "your ideal customer, then press Save and test.",
                "done": ai.settings() is not None,
                "action": lambda: self.go("smart"),
            },
            {
                "title": "Keep a backup",
                "why": "Your searches and leads live only on this computer. A backup on a USB "
                       "stick or in the cloud keeps them safe, and moves them to a new PC.",
                "how": "In Settings, under Your data, press Back up. GeoHarvest also backs up "
                       "by itself once a week and keeps the last four.",
                "done": bool(backup.last_backup()),
                "action": lambda: self.go("settings"),
            },
        ]

    def on_show(self) -> None:
        clear_layout(self.steps_layout)
        steps = self._steps()
        done = sum(1 for step in steps if step["done"])
        self.progress.setRange(0, len(steps))
        self.progress.setValue(done)
        self.progress_label.setText(t("{done} of {count} steps done", done=done,
                                      count=len(steps)))
        set_tone(self.progress_label, "success" if done == len(steps) else "muted")
        for number, step in enumerate(steps, start=1):
            self.steps_layout.addWidget(GuideStep(number, step["title"], step["why"],
                                                  step["how"], step["done"], step["action"]))
