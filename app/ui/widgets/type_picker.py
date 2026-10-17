"""The business-type box on New search: type, or pick from a grouped list that opens below.

The text stays the source of truth ("dentist, cafe, "): the list only adds and
removes entries in it, so saved searches and anything typed by hand work as before.
The list's buttons never take keyboard focus, so clicking them keeps the cursor in
the box, and the list closes when the box loses focus or on Esc.
"""
from __future__ import annotations

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from app.ui import theme
from app.ui.widgets.common import field_label, hint, select_button
from app.ui.widgets.flow import FlowLayout
from app.ui.widgets.inputs import line_edit

BUSINESS_TYPES = [
    ("Marketing and media", [
        "digital marketing agency", "marketing agency", "advertising agency", "SEO agency",
        "social media agency", "PR agency", "branding agency", "web design company",
        "graphic designer", "video production company", "photographer", "printing service"]),
    ("Tech and business", [
        "software company", "IT company", "app developer", "IT support", "cybersecurity company",
        "business consultant", "consultancy", "accountant", "recruitment agency",
        "translation service", "coworking space", "logistics company", "courier service"]),
    ("Legal and finance", [
        "law firm", "lawyer", "notary", "insurance agency", "bank", "financial advisor",
        "mortgage broker", "tax consultant"]),
    ("Property and building", [
        "real estate agency", "property management", "construction company", "builder",
        "home builder", "architect", "interior designer", "contractor", "roofing contractor",
        "electrician", "plumber", "HVAC contractor", "painter", "carpenter", "landscaper",
        "solar energy company"]),
    ("Home services", [
        "cleaning service", "pest control", "moving company", "locksmith", "laundry",
        "tailor", "security company", "storage facility"]),
    ("Health", [
        "dentist", "doctor", "medical clinic", "hospital", "pharmacy", "physiotherapist",
        "chiropractor", "optician", "dermatologist", "psychologist", "veterinarian",
        "medical laboratory", "home care service"]),
    ("Beauty and fitness", [
        "beauty salon", "hair salon", "barber shop", "nail salon", "spa", "massage",
        "cosmetic clinic", "gym", "fitness center", "yoga studio", "pilates studio",
        "tattoo shop"]),
    ("Food and drink", [
        "restaurant", "cafe", "coffee shop", "bakery", "pizza restaurant", "fast food restaurant",
        "bar", "catering", "juice bar", "dessert shop", "food truck"]),
    ("Shops", [
        "supermarket", "grocery store", "clothing store", "shoe store", "jewelry store",
        "electronics store", "mobile phone store", "furniture store", "hardware store",
        "florist", "pet store", "bookstore", "gift shop", "perfume shop", "toy store"]),
    ("Cars and transport", [
        "car dealer", "used car dealer", "car rental", "auto repair shop", "car wash",
        "tire shop", "auto parts store", "driving school", "taxi service", "gas station"]),
    ("Education", [
        "school", "private school", "nursery", "university", "language school",
        "tutoring service", "training center", "music school"]),
    ("Travel and events", [
        "hotel", "travel agency", "tour operator", "event planner", "wedding planner",
        "wedding venue", "event venue"]),
    ("Industry and trade", [
        "manufacturer", "wholesaler", "supplier", "factory", "warehouse",
        "import export company", "packaging company"]),
]


class TypePicker(QWidget):
    """A comma-separated text box with a grouped list of business types under it."""

    def __init__(self, placeholder: str, parent=None):
        super().__init__(parent)
        self.setProperty("role", "plain")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.edit = line_edit(placeholder)
        self.edit.installEventFilter(self)
        self.edit.textChanged.connect(self._sync)
        self.edit.returnPressed.connect(self._add_typed)
        self.textChanged = self.edit.textChanged  # noqa: N815 - same name as QLineEdit's
        layout.addWidget(self.edit)
        # A click on a list button hands focus up the parents to the first that takes it:
        # this widget, which passes it to the box, so the list stays open
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setFocusProxy(self.edit)

        content = QWidget()
        content.setProperty("role", "plain")
        columns = FlowLayout(content, margin=0, spacing=round(18 * theme.text_scale()))
        self.buttons: dict[str, object] = {}
        self.groups: list[tuple[QWidget, list[str]]] = []
        for group, names in BUSINESS_TYPES:
            column = QWidget()
            column.setProperty("role", "plain")
            column.setFixedWidth(round(190 * theme.text_scale()))
            stack = QVBoxLayout(column)
            stack.setContentsMargins(0, 0, 0, 0)
            stack.setSpacing(4)
            stack.addWidget(field_label(group))
            for name in names:
                button = select_button(name)
                button.setProperty("kind", "small")  # a long list: keep it compact
                button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                button.clicked.connect(lambda _on, n=name: self._toggle(n))
                stack.addWidget(button)
                self.buttons[name] = button
            stack.addStretch(1)
            columns.addWidget(column)
            self.groups.append((column, names))
        self.panel = QScrollArea()
        self.panel.setWidgetResizable(True)
        self.panel.setFrameShape(QScrollArea.Shape.NoFrame)
        self.panel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.panel.setWidget(content)
        self.panel.setFixedHeight(round(330 * theme.text_scale()))
        self.panel.hide()
        layout.addWidget(self.panel)
        self.note = hint("Click to pick several. Typing narrows the list; press Enter to add a "
                         "type that isn't listed. Esc closes the list.")
        self.note.hide()
        layout.addWidget(self.note)

    # --- the same calls as the QLineEdit it replaced ---------------------------
    def text(self) -> str:
        return self.edit.text()

    def setText(self, text: str) -> None:  # noqa: N802 - Qt naming
        self.edit.setText(text + ", " if text else "")

    # --- list -------------------------------------------------------------------
    def _parts(self) -> tuple[list[str], str]:
        """(finished entries, the one being typed)."""
        *done, typing = self.edit.text().split(",")
        return [part.strip() for part in done if part.strip()], typing.strip()

    def _write(self, entries: list[str]) -> None:
        self.edit.setText("".join(entry + ", " for entry in entries))

    def _toggle(self, name: str) -> None:
        done, _typing = self._parts()  # what was typed only narrowed the list, so it goes
        lowered = [entry.lower() for entry in done]
        if name.lower() in lowered:
            done.pop(lowered.index(name.lower()))
        else:
            done.append(name)
        self._write(done)

    def _add_typed(self) -> None:
        done, typing = self._parts()
        if typing and typing.lower() not in (entry.lower() for entry in done):
            self._write(done + [typing])

    def _sync(self) -> None:
        done, typing = self._parts()
        chosen = {entry.lower() for entry in done}
        needle = typing.lower()
        for name, button in self.buttons.items():
            button.setChecked(name.lower() in chosen)
            button.setVisible(not needle or needle in name.lower())
        for column, names in self.groups:
            column.setVisible(not needle or any(needle in name.lower() for name in names))

    def _open(self, on: bool) -> None:
        self.panel.setVisible(on)
        self.note.setVisible(on)

    def eventFilter(self, obj, event):  # noqa: N802 - Qt naming
        if event.type() in (QEvent.Type.FocusIn, QEvent.Type.MouseButtonPress):
            self._open(True)
        elif event.type() == QEvent.Type.FocusOut:
            self._open(False)
        elif event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            self._open(False)
            return True
        return super().eventFilter(obj, event)
