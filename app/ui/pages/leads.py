"""Leads: every business found, filterable, sortable and exportable to Excel or CSV."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QFileDialog, QMenu

from app.core import exporter
from app.core import search as searches
from app.ui.pages.base import Page
from app.ui.widgets.common import (Card, copy_to_clipboard, danger_button, hint, muted, open_url,
                                   primary_button, row, secondary_button)
from app.ui.widgets.dialogs import ConfirmDialog
from app.ui.widgets.inputs import Debouncer, combo, line_edit
from app.ui.widgets.leads_model import LEAD_ROLE, LeadsModel, LeadsProxy
from app.ui.widgets.tables import DataTable
from app.workers.ai import AIScoreWorker
from app.workers.base import Task

ALL = "All searches"


class LeadsPage(Page):
    def __init__(self, window):
        super().__init__(window)
        self.add_header("Leads", "Everything GeoHarvest found. Type to filter, click a column "
                                 "heading to sort, then export to Excel.")
        self.search_ids: dict[str, int] = {}
        self.current_id = 0  # 0: all searches

        self.picker = combo([ALL], ALL, on_change=lambda _text: self._load(), translate={ALL})
        self.picker.setMinimumWidth(360)
        self.picker.setMaximumWidth(460)
        self.filter = line_edit("Filter: type a name, city, category, email...")
        self.excel_button = primary_button("Export to Excel", lambda: self.export("xlsx"))
        self.csv_button = secondary_button("Export CSV", lambda: self.export("csv"))
        self.delete_button = danger_button("Delete search...", self.delete_search)
        self.score_button = secondary_button("Score with AI", self.score_with_ai)
        self.score_worker = None
        self.root.addWidget(row(self.picker, self.filter, self.score_button, self.excel_button,
                                self.csv_button, self.delete_button, stretch=1))

        card = Card(padding=12)
        self.count_label = muted("", wrap=False)
        card.add(self.count_label)
        self.model = LeadsModel(self)
        self.proxy = LeadsProxy(self.model, self)
        self.table = DataTable(self.proxy, "No leads yet. Start a search on the New search page.",
                               multi_select=True)
        self.table.view.setSortingEnabled(True)
        self.table.view.sortByColumn(-1, self.table.view.horizontalHeader().sortIndicatorOrder())
        self.table.double_clicked.connect(self._open_row)
        self.table.set_context_menu(self._menu)
        card.add(self.table, 1)
        card.add(hint("Double-click a row to open it in Google Maps. Right-click for more. "
                      "Export saves exactly the rows shown, in this order."))
        self.root.addWidget(card, 1)

        self.debounce = Debouncer(200, self)
        self.debounce.connect(self._apply_filter)
        self.filter.textChanged.connect(lambda _text: self.debounce.poke())
        self.proxy.rowsInserted.connect(self._update_count)
        self.proxy.rowsRemoved.connect(self._update_count)
        self.proxy.modelReset.connect(self._update_count)

        # Columns that are empty everywhere are hidden; re-checked shortly after rows arrive
        self.column_timer = QTimer(self)
        self.column_timer.setSingleShot(True)
        self.column_timer.setInterval(800)
        self.column_timer.timeout.connect(self._hide_empty_columns)

        window.leads_added.connect(self._on_leads_added)
        window.lead_updated.connect(self._on_lead_updated)
        window.lead_removed.connect(
            lambda sid, pid: self.model.remove(pid) if self.current_id in (0, sid) else None)
        window.search_finished.connect(lambda _id: self._refresh_picker())
        self._refresh_picker()
        self._load()

    # --- data ---------------------------------------------------------------
    def on_show(self) -> None:
        self._refresh_picker()

    def _refresh_picker(self) -> None:
        self.search_ids = {}
        labels = [ALL]
        for item in searches.all_searches():
            label = f"{item['title']}  ({item['leads']:,} leads, {item['created'][:10]})"
            self.search_ids[label] = item["id"]
            labels.append(label)
        current = next((lab for lab, sid in self.search_ids.items() if sid == self.current_id), ALL)
        blocked = self.picker.blockSignals(True)
        self.picker.set_values(labels)
        self.picker.setCurrentText(current)
        self.picker.blockSignals(blocked)

    def select_search(self, search_id: int) -> None:
        self._refresh_picker()
        label = next((lab for lab, sid in self.search_ids.items() if sid == search_id), ALL)
        self.picker.setCurrentText(label)
        self._load()

    def _load(self) -> None:
        self.current_id = self.search_ids.get(self.picker.currentText(), 0)
        leads = searches.leads(self.current_id) if self.current_id else searches.all_leads()
        self.model.set_leads(leads)
        self._hide_empty_columns()
        self.delete_button.setEnabled(bool(self.current_id))
        self.score_button.setEnabled(bool(self.current_id) and self.score_worker is None)
        self.score_button.setToolTip("" if self.current_id else
                                     "Pick one search in the list first")

    def _on_leads_added(self, search_id: int, leads: list) -> None:
        if self.current_id == search_id:
            self.model.append(leads)
        elif self.current_id == 0:
            known = self.model._row_of
            self.model.append([lead for lead in leads if lead["place_id"] not in known])
        else:
            return
        self.column_timer.start()

    def _on_lead_updated(self, search_id: int, place_id: str, fields: dict) -> None:
        if self.current_id in (0, search_id):
            self.model.update(place_id, fields)
            self.column_timer.start()

    def _hide_empty_columns(self) -> None:
        empty = set(self.model.empty_columns())
        for column in range(self.model.columnCount()):
            self.table.view.setColumnHidden(column, column in empty)

    def _apply_filter(self) -> None:
        self.proxy.set_filter(self.filter.text())
        self._update_count()

    def _update_count(self, *_args) -> None:
        shown, total = self.proxy.rowCount(), self.model.rowCount()
        self.count_label.setText(f"{total:,} leads" if shown == total
                                 else f"{shown:,} of {total:,} leads match the filter")
        has_rows = shown > 0
        self.excel_button.setEnabled(has_rows)
        self.csv_button.setEnabled(has_rows)

    # --- rows ---------------------------------------------------------------
    def _lead_at(self, proxy_row: int) -> dict | None:
        if proxy_row < 0:
            return None
        return self.proxy.data(self.proxy.index(proxy_row, 0), LEAD_ROLE)

    def _open_row(self, proxy_row: int) -> None:
        lead = self._lead_at(proxy_row)
        if lead and lead.get("maps_url"):
            open_url(lead["maps_url"])

    def _menu(self, proxy_row: int):
        lead = self._lead_at(proxy_row)
        if lead is None:
            return None
        menu = QMenu(self)
        menu.addAction("Open in Google Maps", lambda: open_url(lead["maps_url"]))
        if lead.get("website"):
            menu.addAction("Open website", lambda: open_url(lead["website"]))
        menu.addSeparator()
        for key, label in (("phone", "Copy phone"), ("emails", "Copy emails"),
                           ("website", "Copy website"), ("address", "Copy address")):
            if lead.get(key):
                value = lead[key]
                menu.addAction(label, lambda v=value: copy_to_clipboard(
                    ", ".join(v) if isinstance(v, list) else str(v)))
        return menu

    # --- actions ------------------------------------------------------------
    def export(self, kind: str) -> None:
        leads = self.proxy.visible_leads()
        if not leads:
            return
        title = self.picker.currentText().split("  (")[0] if self.current_id else "All leads"
        safe = "".join(c for c in title if c.isalnum() or c in " ,-_")[:80].strip()
        default = Path.home() / "Documents" / f"GeoHarvest - {safe} - {date.today()}.{kind}"
        wanted = "Excel workbook (*.xlsx)" if kind == "xlsx" else "CSV file (*.csv)"
        path, _ = QFileDialog.getSaveFileName(self, "Export leads", str(default), wanted)
        if not path:
            return
        self.excel_button.setEnabled(False)
        self.notify(f"Exporting {len(leads):,} leads...", "info", 2000)

        def done(count: int) -> None:
            self.notify(f"Saved {count:,} leads to {Path(path).name}", "success", 6000)

        def failed(message: str) -> None:
            self.notify(f"Could not save the file: {message}. Is it open in Excel?", "error", 8000)

        Task(exporter.export, leads, Path(path)).start(
            on_result=self.guard(done), on_error=self.guard(failed),
            on_done=self.guard(self._update_count))

    def score_with_ai(self) -> None:
        from app.core import ai

        if ai.settings() is None:
            self.notify("Set up Smart mode first: open Smart mode in the menu.", "warn")
            return
        leads = self.proxy.visible_leads()
        if not leads or not ConfirmDialog.ask(
                self, "Score these leads with AI?",
                f"The AI will read and score the {len(leads):,} leads shown, using your ideal "
                "customer description. Leads already scored are scored again.",
                confirm_text="Score them"):
            return
        search_id = self.current_id
        worker = AIScoreWorker(search_id, leads)
        worker.signals.updated.connect(
            lambda pid, fields: self.window_.lead_updated.emit(search_id, pid, fields))
        worker.signals.progress.connect(
            lambda done, total, _detail: self.score_button.setText(f"Scoring {done} of {total}"))
        worker.signals.message.connect(lambda text, level: self.notify(text, level))
        worker.signals.finished.connect(
            lambda result: self.notify(f"Scored {result['scored']:,} leads.", "success"))
        worker.signals.failed.connect(lambda message: self.notify(message, "error", 8000))
        worker.signals.done.connect(self._scoring_done)
        self.score_worker = worker
        self.score_button.setEnabled(False)
        self.score_button.setText("Starting...")
        worker.start()

    def _scoring_done(self) -> None:
        self.score_worker = None
        self.score_button.setText("Score with AI")
        self.score_button.setEnabled(bool(self.current_id))

    def busy_reason(self) -> str | None:
        return "leads are being scored" if self.score_worker is not None else None

    def stop(self) -> None:
        if self.score_worker is not None:
            self.score_worker.cancel()

    def delete_search(self) -> None:
        if not self.current_id:
            return
        running = self.window_.page("search")
        if running is not None and running.worker is not None and \
                running.search_id == self.current_id:
            self.notify("That search is still running. Stop it first.", "warn")
            return
        if not ConfirmDialog.ask(self, "Delete this search?",
                                 "Its leads are removed from GeoHarvest. Files you already "
                                 "exported are not touched.",
                                 confirm_text="Delete", danger=True):
            return
        searches.delete(self.current_id)
        self.current_id = 0
        self._refresh_picker()
        self._load()
        self.window_.refresh_status()
