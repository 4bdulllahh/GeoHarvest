"""Smart mode page.

shortcut: placeholder until milestone 5, see docs/handover/README.md.
"""
from __future__ import annotations

from app.ui.pages.base import Page
from app.ui.widgets.common import muted


class SmartPage(Page):
    def __init__(self, window):
        super().__init__(window)
        self.add_header("Smart mode", "Connect an AI and describe your ideal customer. It checks every lead and scores it.")
        self.root.addWidget(muted("Coming in milestone 5."))
        self.root.addStretch(1)
