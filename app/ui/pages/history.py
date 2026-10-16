"""Past searches page.

shortcut: placeholder until milestone 6, see docs/handover/README.md.
"""
from __future__ import annotations

from app.ui.pages.base import Page
from app.ui.widgets.common import muted


class HistoryPage(Page):
    def __init__(self, window):
        super().__init__(window)
        self.add_header("Past searches", "Reopen an old search, or resume one that was stopped.")
        self.root.addWidget(muted("Coming in milestone 6."))
        self.root.addStretch(1)
