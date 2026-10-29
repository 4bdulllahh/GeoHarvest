"""Past searches: reopen the leads of any search, resume a stopped one, or run it again."""
from __future__ import annotations

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt

from app.core import prefs
from app.core import search as searches
from app.ui.pages.base import Page
from app.ui.widgets.common import Card, danger_button, hint, primary_button, row, secondary_button
from app.ui.widgets.dialogs import ConfirmDialog
from app.ui.widgets.tables import DataTable

STATUS = {"done": "Finished", "stopped": "Stopped, can resume", "running": "Running now",
          "failed": "Stopped by an error"}
HEADERS = ["Search", "Leads", "Status", "Started", "Last activity"]


class SearchesModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: list[dict] = []

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802, B008
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802, B008
        return 0 if parent.isValid() else len(HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return HEADERS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role not in (Qt.ItemDataRole.DisplayRole,
                                               Qt.ItemDataRole.ToolTipRole):
            return None
        item = self.rows[index.row()]
        return [item["title"], f"{item['leads']:,}", STATUS.get(item["status"], item["status"]),
                prefs.format_datetime(item["created"]),
                prefs.format_datetime(item["updated"])][index.column()]

    def load(self, rows: list[dict]) -> None:
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()


class HistoryPage(Page):
    def __init__(self, window):
        super().__init__(window)
        self.add_header("Past searches", "Every search you have run. Load its leads, resume one "
                                         "that stopped (closing the app, pressing Stop, or Google "
                                         "asking to slow down), or run it again for new businesses.")
        self.model = SearchesModel(self)
        self.table = DataTable(self.model, "No searches yet. Start one on the New search page.")
        self.table.double_clicked.connect(lambda _row: self.load())
        self.table.selection_changed.connect(self._update_buttons)

        self.open_button = primary_button("Load", self.load)
        self.resume_button = secondary_button("Resume", self.resume)
        self.again_button = secondary_button("Run again", self.run_again)
        self.delete_button = danger_button("Delete...", self.delete)
        self.root.addWidget(row(self.open_button, self.resume_button, self.again_button, None,
                                self.delete_button))
        card = Card(padding=12)
        card.add(self.table, 1)
        card.add(hint("Resume carries on where the search stopped: finished cities are skipped "
                      "and nothing found so far is lost. Run again starts the same search fresh "
                      "with your current Smart mode setup."))
        self.root.addWidget(card, 1)
        window.search_finished.connect(lambda _id: self.on_show())
        self.on_show()

    def on_show(self) -> None:
        self.model.load(searches.all_searches())
        self._update_buttons()

    def _selected(self) -> dict | None:
        index = self.table.selected_row()
        return self.model.rows[index] if 0 <= index < len(self.model.rows) else None

    def _search_page(self):
        return self.window_.ensure_page("search")

    def _update_buttons(self) -> None:
        item = self._selected()
        busy = self._search_page().worker is not None
        for button in (self.open_button, self.again_button, self.delete_button):
            button.setEnabled(item is not None)
        self.resume_button.setEnabled(item is not None and item["status"] != "done" and not busy)
        self.again_button.setEnabled(item is not None and not busy)

    def load(self) -> None:
        """Put this search's leads on the Leads page, staying here."""
        item = self._selected()
        if item is None:
            return
        self.window_.ensure_page("leads").select_search(item["id"])
        self.notify(f"Search loaded ({item['leads']:,} leads). Check the Leads tab.", "success")

    def resume(self) -> None:
        item = self._selected()
        if item is None:
            return
        page = self._search_page()
        self.window_.show_page("search")
        page.load_options(searches.get(item["id"])["options"])
        page.run(item["id"])

    def run_again(self) -> None:
        item = self._selected()
        if item is None:
            return
        page = self._search_page()
        self.window_.show_page("search")
        page.load_options(searches.get(item["id"])["options"])
        page.start()

    def delete(self) -> None:
        item = self._selected()
        if item is None:
            return
        page = self._search_page()
        if page.worker is not None and page.search_id == item["id"]:
            self.notify("That search is running. Stop it first.", "warn")
            return
        if not ConfirmDialog.ask(self, "Delete this search?",
                                 f"'{item['title']}' and its {item['leads']:,} leads are removed "
                                 "from GeoHarvest. Files you already exported are not touched.",
                                 confirm_text="Delete", danger=True):
            return
        searches.delete(item["id"])
        self.on_show()
        self.window_.refresh_status()
