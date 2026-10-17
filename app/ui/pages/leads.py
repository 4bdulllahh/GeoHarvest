"""Leads: every business found, filterable, sortable and exportable to Excel or CSV."""
from __future__ import annotations

from datetime import date
from html import escape
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QMenu,
                             QScrollArea, QVBoxLayout, QWidget)

from app.core import db, exporter
from app.core import search as searches
from app.core.exporter import LINK_COLUMNS
from app.core.places import FIELD_GROUPS, FIELDS, HEADERS
from app.ui import theme
from app.ui.pages.base import Page
from app.ui.widgets.common import (Card, copy_to_clipboard, danger_button, flow_row, hint, muted,
                                   open_url, primary_button, row, secondary_button)
from app.ui.widgets.dialogs import ConfirmDialog
from app.ui.widgets.inputs import Debouncer, checkbox, combo, line_edit
from app.ui.widgets.leads_model import LEAD_ROLE, LeadsModel, LeadsProxy
from app.ui.widgets.tables import DataTable
from app.workers.ai import AIScoreWorker
from app.workers.base import Task

ALL = "All searches"


def text_label(text: str, role: str = "") -> QLabel:
    label = QLabel(text)
    if role:
        label.setProperty("role", role)
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.PlainText)  # business names come from Google: never HTML
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def as_text(value) -> str:
    return ", ".join(map(str, value)) if isinstance(value, list) else str(value)


class ColumnsDialog(QDialog):
    """Switch columns of the Leads table (and the export) on and off, grouped as on New search."""

    def __init__(self, parent: QWidget, chosen: set[str], empty: set[str], apply):
        super().__init__(parent)
        scale = theme.text_scale()
        self.setWindowTitle("Columns")
        self.resize(round(760 * scale), round(640 * scale))
        pad = round(22 * scale)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(pad, pad, pad, pad)
        layout.setSpacing(round(8 * scale))
        layout.addWidget(text_label("Columns", "heading"))
        layout.addWidget(text_label("Switch off what you don't need. Export saves only the "
                                    "columns that are on. Columns marked \"no data\" have "
                                    "nothing in them for these leads, so they stay hidden.",
                                    "muted"))
        content = QWidget()
        content.setProperty("role", "plain")
        inner = QVBoxLayout(content)
        inner.setContentsMargins(0, 0, round(8 * scale), 0)
        self.boxes = {}
        for group, keys in FIELD_GROUPS:
            container, flow = flow_row(spacing=14)
            for key in keys:
                label = HEADERS[key] + (" (no data)" if key in empty else "")
                box = checkbox(label, key in chosen or key == "name",
                               on_change=lambda _on: apply(self.chosen()))
                self.boxes[key] = box
                flow.addWidget(box)
            inner.addWidget(text_label(group, "subheading"))
            inner.addWidget(container)
        self.boxes["name"].setEnabled(False)
        inner.addStretch(1)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.Shape.NoFrame)
        area.setWidget(content)
        layout.addWidget(area, 1)
        buttons = QHBoxLayout()
        buttons.addWidget(secondary_button("All on", lambda: self._all(True)))
        buttons.addWidget(secondary_button("All off", lambda: self._all(False)))
        buttons.addStretch(1)
        buttons.addWidget(primary_button("Done", self.accept, width=120))
        layout.addLayout(buttons)

    def _all(self, on: bool) -> None:
        for key, box in self.boxes.items():
            box.setChecked(on or key == "name")

    def chosen(self) -> set[str]:
        return {key for key, box in self.boxes.items() if box.isChecked()}


class LeadDialog(QDialog):
    """Everything known about one business, opened by double-clicking its row."""

    def __init__(self, parent: QWidget, lead: dict):
        super().__init__(parent)
        scale = theme.text_scale()
        self.setWindowTitle(lead.get("name") or "Lead")
        self.resize(round(600 * scale), round(640 * scale))
        pad = round(22 * scale)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(pad, pad, pad, pad)
        layout.setSpacing(round(8 * scale))
        layout.addWidget(text_label(lead.get("name") or "", "heading"))
        if lead.get("category"):
            layout.addWidget(text_label(lead["category"], "muted"))

        filled = [(key, header, as_text(lead[key])) for key, header in FIELDS
                  if lead.get(key) not in (None, "", [])]
        content = QWidget()
        content.setProperty("role", "plain")
        form = QFormLayout(content)
        form.setContentsMargins(0, round(6 * scale), round(8 * scale), 0)
        form.setHorizontalSpacing(round(16 * scale))
        form.setVerticalSpacing(round(8 * scale))
        for key, header, text in filled:
            if key in ("name", "category"):
                continue
            if key in LINK_COLUMNS and text.startswith(("http://", "https://")):
                value = QLabel(f'<a href="{escape(text, quote=True)}">{escape(text)}</a>')
                value.setWordWrap(True)
                value.setOpenExternalLinks(True)
            else:
                value = text_label(text)
            form.addRow(text_label(header, "muted"), value)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.Shape.NoFrame)
        area.setWidget(content)
        layout.addWidget(area, 1)

        summary = "\n".join(f"{header}: {text}" for _key, header, text in filled)
        buttons = QHBoxLayout()
        buttons.addWidget(secondary_button("Copy all", lambda: copy_to_clipboard(summary)))
        if lead.get("maps_url"):
            buttons.addWidget(secondary_button("Open in Google Maps",
                                               lambda: open_url(lead["maps_url"])))
        buttons.addStretch(1)
        buttons.addWidget(primary_button("Close", self.accept, width=120))
        layout.addLayout(buttons)


class LeadsPage(Page):
    def __init__(self, window):
        super().__init__(window)
        self.add_header("Leads", "Everything GeoHarvest found. Type to filter, click a column "
                                 "heading to sort, then export to Excel.")
        self.search_ids: dict[str, int] = {}
        self.current_id = 0  # 0: all searches
        newest = searches.all_searches()[:1]
        if newest:  # open on the search the user ran last
            self.current_id = newest[0]["id"]

        self.picker = combo([ALL], ALL, on_change=lambda _text: self._load(), translate={ALL})
        self.picker.setMinimumWidth(360)
        self.picker.setMaximumWidth(460)
        self.filter = line_edit("Filter: type a name, city, category, email...")
        self.excel_button = primary_button("Export to Excel", lambda: self.export("xlsx"))
        self.csv_button = secondary_button("More exports")
        exports = QMenu(self.csv_button)
        exports.addAction("CSV file", lambda: self.export("csv"))
        exports.addSeparator()
        for crm, (name, _columns) in exporter.CRMS.items():
            exports.addAction(f"CSV for {name}", lambda c=crm: self.export(c))
        exports.addSeparator()
        exports.addAction("Copy for Google Sheets", self.copy_for_sheets)
        self.csv_button.setMenu(exports)
        self.columns_button = secondary_button("Columns...", self.choose_columns)
        self.delete_button = danger_button("Delete search...", self.delete_search)
        self.delete_leads_button = secondary_button("Delete selected", self.delete_selected)
        self.score_button = secondary_button("Score with AI", self.score_with_ai)
        self.score_worker = None
        self.root.addWidget(row(self.picker, self.filter, self.score_button, self.excel_button,
                                self.csv_button, self.delete_button, stretch=1))

        card = Card(padding=12)
        self.count_label = muted("", wrap=False)
        card.add(row(self.count_label, self.columns_button, self.delete_leads_button, stretch=0))
        self.model = LeadsModel(self)
        self.proxy = LeadsProxy(self.model, self)
        self.table = DataTable(self.proxy, "No leads yet. Start a search on the New search page.",
                               multi_select=True)
        self.table.view.setSortingEnabled(True)
        self.table.view.sortByColumn(-1, self.table.view.horizontalHeader().sortIndicatorOrder())
        self.table.double_clicked.connect(self._open_row)
        self.table.set_context_menu(self._menu)
        self.table.selection_changed.connect(self._update_count)
        QShortcut(QKeySequence.StandardKey.Delete, self.table.view, self.delete_selected,
                  context=Qt.ShortcutContext.WidgetShortcut)
        card.add(self.table, 1)
        card.add(hint("Double-click a row to see everything about that business. Right-click "
                      "for more. Export saves exactly the rows and columns shown, in this order."))
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

        window.lead_updated.connect(self._on_lead_updated)
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
        record = searches.get(self.current_id) if self.current_id else None
        self.fields = set(record["options"]["fields"] if record else
                          db.get_setting("all_searches_fields", [k for k, _ in FIELDS]))
        self.model.set_leads(leads)
        self._hide_empty_columns()
        self.delete_button.setEnabled(bool(self.current_id))
        self.score_button.setEnabled(bool(self.current_id) and self.score_worker is None)
        self.score_button.setToolTip("" if self.current_id else
                                     "Pick one search in the list first")

    def _on_lead_updated(self, search_id: int, place_id: str, fields: dict) -> None:
        if self.current_id in (0, search_id):
            self.model.update(place_id, fields)
            self.column_timer.start()

    def _hide_empty_columns(self) -> None:
        """Columns the search left out, or empty in every row, stay hidden."""
        empty = set(self.model.empty_columns())
        for column, key in enumerate(self.model.keys):
            self.table.view.setColumnHidden(column, column in empty or key not in self.fields)

    def choose_columns(self) -> None:
        def apply(chosen: set[str]) -> None:
            self.fields = chosen
            self._hide_empty_columns()

        empty = {self.model.keys[column] for column in self.model.empty_columns()}
        ColumnsDialog(self.window(), self.fields, empty, apply).exec()
        keys = [key for key, _ in FIELDS if key in self.fields]
        if self.current_id:
            searches.set_fields(self.current_id, keys)
        else:
            db.set_setting("all_searches_fields", keys)

    def _shown_keys(self) -> list[str]:
        return [key for column, key in enumerate(self.model.keys)
                if not self.table.view.isColumnHidden(column)]

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
        self.delete_leads_button.setEnabled(bool(self.table.selected_rows()))

    # --- rows ---------------------------------------------------------------
    def _lead_at(self, proxy_row: int) -> dict | None:
        if proxy_row < 0:
            return None
        return self.proxy.data(self.proxy.index(proxy_row, 0), LEAD_ROLE)

    def _open_row(self, proxy_row: int) -> None:
        lead = self._lead_at(proxy_row)
        if lead:
            LeadDialog(self.window(), lead).exec()

    def _menu(self, proxy_row: int):
        lead = self._lead_at(proxy_row)
        if lead is None:
            return None
        menu = QMenu(self)
        menu.addAction("Show details", lambda: self._open_row(proxy_row))
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
        menu.addSeparator()
        menu.addAction("Delete selected", self.delete_selected)
        return menu

    # --- actions ------------------------------------------------------------
    def copy_for_sheets(self) -> None:
        leads = self.proxy.visible_leads()
        if not leads:
            return
        copy_to_clipboard(exporter.to_tsv(leads, self._shown_keys()))
        open_url("https://sheets.new")
        self.notify(f"Copied {len(leads):,} leads. A new Google Sheet is opening in your "
                    "browser: click cell A1 and press Ctrl+V.", "success", 10000)

    def export(self, kind: str) -> None:
        """kind: xlsx, csv, or a CRM from exporter.CRMS (a CSV in that CRM's columns)."""
        leads = self.proxy.visible_leads()
        if not leads:
            return
        crm = exporter.CRMS.get(kind)
        suffix = "xlsx" if kind == "xlsx" else "csv"
        title = self.picker.currentText().split("  (")[0] if self.current_id else "All leads"
        safe = "".join(c for c in title if c.isalnum() or c in " ,-_")[:80].strip()
        name = f"GeoHarvest - {safe}{f' - {crm[0]}' if crm else ''} - {date.today()}.{suffix}"
        default = Path.home() / "Documents" / name
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

        job = Task(exporter.to_crm, leads, Path(path), kind) if crm else \
            Task(exporter.export, leads, Path(path), self._shown_keys())
        job.start(
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

    def delete_selected(self) -> None:
        leads = [lead for row in self.table.selected_rows() if (lead := self._lead_at(row))]
        if not leads:
            return
        many = len(leads) > 1
        where = "this search" if self.current_id else "every search that found it"
        if not ConfirmDialog.ask(
                self, f"Delete {len(leads):,} leads?" if many else
                f"Delete {leads[0].get('name') or 'this lead'}?",
                f"{'They are' if many else 'It is'} removed from {where}. Files you already "
                "exported are not touched.", confirm_text="Delete", danger=True):
            return
        place_ids = [lead["place_id"] for lead in leads]
        searches.delete_leads(place_ids, self.current_id)
        for place_id in place_ids:
            self.model.remove(place_id)
        self.notify(f"Deleted {len(leads):,} {'leads' if many else 'lead'}.", "success")
        self._refresh_picker()  # lead counts in the search list
        self.window_.refresh_status()

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
