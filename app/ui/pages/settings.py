"""Settings: appearance, search speed, updates and the user's data."""
from __future__ import annotations

import os

from app import config
from app.core import db, prefs
from app.ui.pages.base import Page
from app.ui.widgets.common import (ChoiceButtons, FormRow, Section, danger_button, hint, muted,
                                   open_url, row, secondary_button)
from app.ui.widgets.dialogs import ConfirmDialog
from app.ui.widgets.inputs import checkbox

SPEEDS = [("2", "Gentle"), ("4", "Normal"), ("8", "Fast")]


class SettingsPage(Page):
    def __init__(self, window):
        super().__init__(window)
        self.add_header("Settings", "How GeoHarvest looks and behaves.")
        body = self.scroll_body()
        layout = body.body_layout

        look = Section("Appearance")
        theme_row = FormRow("Theme")
        theme_row.add(ChoiceButtons(prefs.THEMES, prefs.get("appearance"),
                                    on_change=window.change_appearance))
        look.add(theme_row)
        size_row = FormRow("Text size")
        size_row.add(ChoiceButtons([(k, label) for k, label, _ in prefs.TEXT_SIZES],
                                   prefs.get("text_size"), on_change=window.change_text_size))
        look.add(size_row)
        look.add(checkbox("High contrast", bool(prefs.get("high_contrast")),
                          on_change=window.change_contrast))
        look.add(checkbox("Bold text", bool(prefs.get("bold_text")),
                          on_change=window.change_bold_text))
        layout.addWidget(look)

        speed = Section("Search speed",
                        "How many cities GeoHarvest searches at the same time.")
        speed.add(ChoiceButtons(SPEEDS, str(db.get_setting("parallel_searches", 4)),
                                on_change=lambda v: db.set_setting("parallel_searches", int(v))))
        speed.add(hint("Fast finishes big searches sooner, but Google is more likely to ask "
                       "GeoHarvest to slow down. If that happens, the search pauses and you can "
                       "resume it later from Past searches. Applies to the next search."))
        layout.addWidget(speed)

        updates = Section("Updates", f"You have GeoHarvest {config.APP_VERSION}.")
        updates.add(checkbox("Check for a new version when GeoHarvest opens",
                             bool(db.get_setting("check_updates", True)),
                             on_change=lambda on: db.set_setting("check_updates", bool(on))))
        updates.add(row(secondary_button("Check now",
                                         lambda: window.check_for_update(tell_if_none=True)),
                        secondary_button("Open the GitHub page",
                                         lambda: open_url(config.REPO_URL)), None))
        layout.addWidget(updates)

        data = Section("Your data",
                       "Searches, leads, settings and your encrypted AI key are kept on this "
                       "computer only, in your user folder. Updating GeoHarvest never touches them.")
        data.add(row(secondary_button("Open the data folder",
                                      lambda: os.startfile(config.DATA_DIR)),  # noqa: S606
                     danger_button("Delete all searches and leads...", self.delete_all), None))
        layout.addWidget(data)

        fair = Section("Use it fairly")
        fair.add(muted("GeoHarvest reads public Google Maps listings and business websites. "
                       "When you contact the businesses you find, follow the rules where you "
                       "and they are, such as GDPR in the EU and UK, CAN-SPAM in the US and the "
                       "UAE's data protection law, and Google's terms of service."))
        layout.addWidget(fair)
        layout.addStretch(1)

    def delete_all(self) -> None:
        if self.window_.busy_page_reason():
            self.notify("Wait until the search has finished, or stop it first.", "warn")
            return
        if not ConfirmDialog.ask(self, "Delete every search and lead?",
                                 "This empties GeoHarvest's lead lists. Files you exported are "
                                 "not touched, and your settings and AI key are kept.",
                                 confirm_text="Delete everything", danger=True):
            return
        db.execute("DELETE FROM leads")
        db.execute("DELETE FROM searches")
        self.window_.refresh_status()
        self.notify("All searches and leads deleted.", "success")
