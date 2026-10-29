"""The leads table: a model over lead dicts, and a proxy that sorts and filters it.

Rows arrive in batches of up to 20 while a search runs, so appending is an
insert, never a reset. Typing in the filter box matches against one lowercase
string per row, built once, instead of asking every cell of every row.
"""
from __future__ import annotations

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt

from app.core import prefs
from app.core.enrich import STARTUP_YEARS
from app.core.places import FIELDS
from app.core.search import SOCIALS, has_link
from app.i18n import t
from app.ui import theme

NUMERIC = {"quality", "rating", "reviews", "latitude", "longitude", "ai_score"}
DATES = {"found", "exported", "domain_created"}  # ISO dates, shown in the user's date format
SORT_ROLE = Qt.ItemDataRole.UserRole
LEAD_ROLE = Qt.ItemDataRole.UserRole + 1
DESCENDING = Qt.SortOrder.DescendingOrder
ASCENDING = Qt.SortOrder.AscendingOrder

# The Sort menu on the Leads page: key -> (column, order). "rank" is the order the search
# ranked them in (no column sorted).
SORTS = {
    "rank": (None, ASCENDING), "quality": ("quality", DESCENDING),
    "name": ("name", ASCENDING), "name_za": ("name", DESCENDING),
    "rating": ("rating", DESCENDING), "rating_low": ("rating", ASCENDING),
    "reviews": ("reviews", DESCENDING), "reviews_few": ("reviews", ASCENDING),
    "ai": ("ai_score", DESCENDING), "city": ("city", ASCENDING),
    "newest": ("found", DESCENDING), "oldest": ("found", ASCENDING),
}
SORT_MENU = [
    ("rank", "Best leads first"), ("quality", "Quality score, high to low"),
    ("ai", "AI score, high to low"), None,
    ("name", "Name, A to Z"), ("name_za", "Name, Z to A"), ("city", "City, A to Z"), None,
    ("rating", "Rating, high to low"), ("rating_low", "Rating, low to high"),
    ("reviews", "Most reviews"), ("reviews_few", "Fewest reviews"), None,
    ("newest", "Found most recently"), ("oldest", "Found longest ago"),
]


def _age(lead: dict):
    years = lead.get("age_years")
    return years if isinstance(years, (int, float)) else None


# The Show menu: which leads to list
SHOWS = {
    "all": lambda lead: True,
    "email": lambda lead: bool(lead.get("emails")),
    "phone": lambda lead: bool(lead.get("phone")),
    "email_phone": lambda lead: bool(lead.get("emails")) and bool(lead.get("phone")),
    "website": lambda lead: bool(lead.get("website")),
    "no_website": lambda lead: not lead.get("website"),
    "owner": lambda lead: bool(lead.get("owner_name")),
    "social": lambda lead: any(has_link(lead, key) for key in SOCIALS),
    "linkedin": lambda lead: has_link(lead, "linkedin") or has_link(lead, "owner_linkedin"),
    "startup": lambda lead: _age(lead) is not None and _age(lead) < STARTUP_YEARS,
    "established": lambda lead: _age(lead) is not None and _age(lead) >= STARTUP_YEARS,
    "good_fit": lambda lead: lead.get("ai_verdict") == "Good fit",
    "new": lambda lead: not lead.get("exported"),
}
SHOW_MENU = [
    ("all", "All leads"), None,
    ("email", "With an email"), ("phone", "With a phone number"),
    ("email_phone", "With an email and a phone"), ("website", "With a website"),
    ("no_website", "Without a website"), ("owner", "With the owner's name"),
    ("social", "On social media"), ("linkedin", "On LinkedIn"), None,
    ("startup", "Startups"), ("established", "Established companies"),
    ("good_fit", "AI says good fit"), None,
    ("new", "Not exported yet"),
]


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
            return t(self.headers[section])
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
            if key in DATES:
                return prefs.format_date(value)
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
        self._show = SHOWS["all"]
        self._rating: tuple | None = None   # (low, high); None: any rating
        self._reviews: tuple | None = None  # (low, high or None for no maximum)
        self._dates: tuple | None = None    # (first, last) ISO days the lead was found

    def set_filter(self, text: str) -> None:
        self._needle = text.strip().lower()
        self.invalidateFilter()

    def set_show(self, key: str) -> None:
        self._show = SHOWS.get(key, SHOWS["all"])
        self.invalidateFilter()

    def set_ranges(self, rating: tuple | None, reviews: tuple | None) -> None:
        self._rating, self._reviews = rating, reviews
        self.invalidateFilter()

    def set_dates(self, first, last) -> None:
        self._dates = (first.isoformat(), last.isoformat()) if first and last else None
        self.invalidateFilter()

    def filterAcceptsRow(self, row: int, parent) -> bool:  # noqa: N802 - Qt naming
        source = self.sourceModel()
        lead = source.leads[row]
        if not self._show(lead):
            return False
        if self._rating:
            rating = lead.get("rating")
            if not isinstance(rating, (int, float)) or \
                    not self._rating[0] <= rating <= self._rating[1]:
                return False
        if self._reviews:
            count = lead.get("reviews") or 0
            if count < self._reviews[0] or (self._reviews[1] is not None
                                            and count > self._reviews[1]):
                return False
        found = str(lead.get("found") or "")[:10]
        if self._dates and not self._dates[0] <= found <= self._dates[1]:
            return False
        if not self._needle:
            return True
        return all(word in source.haystacks[row] for word in self._needle.split())

    def visible_leads(self) -> list[dict]:
        """The leads in the order and filter shown on screen, for export."""
        return [self.data(self.index(row, 0), LEAD_ROLE) for row in range(self.rowCount())]
