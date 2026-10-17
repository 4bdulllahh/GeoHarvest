"""A searchable list of tick boxes, for choosing countries and cities."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from app.ui.widgets.common import hint, row, small_button
from app.ui.widgets.inputs import line_edit

KEY = Qt.ItemDataRole.UserRole


class CheckList(QWidget):
    """Items have a key (stored) and a label (shown). ``changed`` fires once per user action."""

    changed = pyqtSignal()
    toggled = pyqtSignal(str, bool)  # one item ticked or unticked by the user

    def __init__(self, placeholder: str, height: int = 260, parent=None):
        super().__init__(parent)
        self.setProperty("role", "plain")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.filter = line_edit(placeholder)
        self.filter.textChanged.connect(self._apply_filter)
        self.all_button = small_button("All", lambda: self.set_all(True))
        self.none_button = small_button("None", lambda: self.set_all(False))
        layout.addWidget(row(self.filter, self.all_button, self.none_button, stretch=0))
        self.list = QListWidget()
        self.list.setUniformItemSizes(True)
        self.list.setFixedHeight(height)
        self.list.itemChanged.connect(self._item_changed)
        layout.addWidget(self.list)
        self.count = hint("")
        layout.addWidget(self.count)
        self._quiet = False

    # --- contents -----------------------------------------------------------
    def set_items(self, items: list[tuple[str, str]], checked: set[str]) -> None:
        """Replace the list. ``items`` is (key, label); ``checked`` the keys to tick."""
        self._quiet = True
        self.list.clear()
        for key, label in items:
            item = QListWidgetItem(label)
            item.setData(KEY, key)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if key in checked else
                               Qt.CheckState.Unchecked)
            self.list.addItem(item)
        self._quiet = False
        self._apply_filter()

    def keys(self) -> list[str]:
        return [self.list.item(i).data(KEY) for i in range(self.list.count())]

    def checked(self) -> list[str]:
        return [self.list.item(i).data(KEY) for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.CheckState.Checked]

    def set_checked(self, keys: set[str], value: bool = True) -> None:
        self._quiet = True
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.data(KEY) in keys:
                item.setCheckState(Qt.CheckState.Checked if value else Qt.CheckState.Unchecked)
        self._quiet = False
        self._update_count()

    def set_all(self, value: bool) -> None:
        """Tick or untick every item the filter is showing."""
        self.set_checked({self.list.item(i).data(KEY) for i in range(self.list.count())
                          if not self.list.item(i).isHidden()}, value)
        self.changed.emit()

    # --- internals ----------------------------------------------------------
    def _item_changed(self, item: QListWidgetItem) -> None:
        if self._quiet:
            return
        self.toggled.emit(item.data(KEY), item.checkState() == Qt.CheckState.Checked)
        self._update_count()
        self.changed.emit()

    def _apply_filter(self) -> None:
        needle = self.filter.text().strip().lower()
        for i in range(self.list.count()):
            item = self.list.item(i)
            item.setHidden(bool(needle) and needle not in item.text().lower())
        self._update_count()

    def _update_count(self) -> None:
        ticked = [self.list.item(i).text() for i in range(self.list.count())
                  if self.list.item(i).checkState() == Qt.CheckState.Checked]
        summary = f"{len(ticked):,} of {self.list.count():,} chosen"
        # A few ticks are easy to lose in a long list, so name them
        self.count.setText(summary + (": " + ", ".join(ticked) if 0 < len(ticked) <= 6 else ""))
