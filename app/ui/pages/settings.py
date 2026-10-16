"""Settings page: appearance now; scraping speed and updates arrive in milestone 6."""
from __future__ import annotations

from app.core import prefs
from app.ui.pages.base import Page
from app.ui.widgets.common import ChoiceButtons, FormRow, Section
from app.ui.widgets.inputs import checkbox


class SettingsPage(Page):
    def __init__(self, window):
        super().__init__(window)
        self.add_header("Settings", "How MapScout looks and behaves.")
        body = self.scroll_body()

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
        body.body_layout.addWidget(look)
        body.body_layout.addStretch(1)
