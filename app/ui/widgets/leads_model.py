"""The leads table: a model over lead dicts, and a proxy that sorts and filters it.

Rows arrive in batches of up to 20 while a search runs, so appending is an
insert, never a reset. Typing in the filter box matches against one lowercase
string per row, built once, instead of asking every cell of every row.
"""
from __future__ import annotations

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt

from app.core.places import FIELDS
from app.ui import theme

NUMERIC = {"rating", "reviews", "latitude", "longitude", "ai_score"}
SORT_ROLE = Qt.ItemDataRole.UserRole
LEAD_ROLE = Qt.ItemDataRole.UserRole + 1


class LeadsModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.keys = [key for key, _ in FIELDS]
        self.headers = [header for _, header in FIELDS]
        self.leads: list[dict] = []
        self.haystacks: list[str] = []
        self._row_of: dict[str, int] = {}

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802, B008
        return 0 if parent.isValid() else len(self.leads)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802, B008
        return 0 if parent.isValid() else len(self.keys)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.headers[section]
        return None

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        lead = self.leads[index.row()]
        key = self.keys[index.column()]
        value = lead.get(key)
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            if value is None:
                return ""
            if isinstance(value, list):
                return ", ".join(map(str, value))
            return str(value)
        if role == SORT_ROLE:
            if key in NUMERIC:
                return float(value) if isinstance(value, (int, float)) else -1.0
            return str(value or "").lower()
        if role == LEAD_ROLE:
            return lead
        if role == Qt.ItemDataRole.ForegroundRole:
            if key == "status" and value and value != "Open":
                return theme.qcolor("error")
            if key == "ai_verdict" and value:
                return theme.qcolor({"Good fit": "success", "Maybe": "warning"}.get(value, "error"))
        return None

    # --- loading ------------------------------------------------------------
    @staticmethod
    def _haystack(lead: dict) -> str:
        return " ".join(str(v) for v in lead.values() if v not in (None, "")).lower()

    def set_leads(self, leads: list[dict]) -> None:
        self.beginResetModel()
        self.leads = list(leads)
        self.haystacks = [self._haystack(lead) for lead in self.leads]
        self._row_of = {lead.get("place_id"): row for row, lead in enumerate(self.leads)}
        self.endResetModel()

    def append(self, leads: list[dict]) -> None:
        if not leads:
            return
        start = len(self.leads)
        self.beginInsertRows(QModelIndex(), start, start + len(leads) - 1)
        for offset, lead in enumerate(leads):
            self.leads.append(lead)
            self.haystacks.append(self._haystack(lead))
            self._row_of[lead.get("place_id")] = start + offset
        self.endInsertRows()

    def update(self, place_id: str, fields: dict) -> None:
        """Merge new fields (emails, AI score) into a row already on screen."""
        row = self._row_of.get(place_id)
        if row is None:
            return
        self.leads[row].update(fields)
        self.haystacks[row] = self._haystack(self.leads[row])
        self.dataChanged.emit(self.index(row, 0), self.index(row, len(self.keys) - 1))

    def remove(self, place_id: str) -> None:
        row = self._row_of.pop(place_id, None)
        if row is None:
            return
        self.beginRemoveRows(QModelIndex(), row, row)
        del self.leads[row]
        del self.haystacks[row]
        self.endRemoveRows()
        for later in self.leads[row:]:
            self._row_of[later.get("place_id")] -= 1

    def empty_columns(self) -> list[int]:
        return [column for column, key in enumerate(self.keys)
                if not any(lead.get(key) not in (None, "", []) for lead in self.leads)]


class LeadsProxy(QSortFilterProxyModel):
    def __init__(self, source: LeadsModel, parent=None):
        super().__init__(parent)
        self.setSourceModel(source)
        self.setSortRole(SORT_ROLE)
        self._needle = ""

    def set_filter(self, text: str) -> None:
        self._needle = text.strip().lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, row: int, parent) -> bool:  # noqa: N802 - Qt naming
        if not self._needle:
            return True
        haystack = self.sourceModel().haystacks[row]
        return all(word in haystack for word in self._needle.split())

    def visible_leads(self) -> list[dict]:
        """The leads in the order and filter shown on screen, for export."""
        return [self.data(self.index(row, 0), LEAD_ROLE) for row in range(self.rowCount())]
