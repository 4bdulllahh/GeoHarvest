"""Two-handle min/max slider (from HomingPigeon), over a table of steps.

Qt ships a single-handle QSlider, so this paints its own. Values snap to the
step table rather than a linear scale, so the part people use (ratings 4 to 5,
reviews 0 to 100) gets most of the room.
"""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from app.ui import theme


def nearest_index(steps: list, value) -> int:
    return min(range(len(steps)), key=lambda i: abs(steps[i] - value))


class RangeSlider(QWidget):
    """Pick a low and a high value from ``steps`` (ascending). ``label`` writes a value
    under its handle."""

    changed = pyqtSignal(object, object)   # live, while dragging
    released = pyqtSignal(object, object)  # once, when the handle is let go

    TRACK_HEIGHT = 4
    SIDE_PAD = 22

    def __init__(self, steps: list, low, high, label: Callable[[object], str] = str,
                 parent=None):
        super().__init__(parent)
        self.setProperty("role", "plain")
        # Drawn by hand with the lowest value on the left. It stays that way in
        # Arabic too, like a ruler, so the painting and the mouse agree.
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.steps = list(steps)
        self.label = label
        self._low = self._high = 0
        self.set(low, high)
        self._dragging: str | None = None
        self._hover: str | None = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(self._natural_height())
        self.setMinimumWidth(round(180 * theme.text_scale()))

    # --- metrics ------------------------------------------------------------
    def _radius(self) -> float:
        return 9 * theme.text_scale()

    def _natural_height(self) -> int:
        return int(46 * theme.text_scale())

    def sizeHint(self):  # noqa: N802 - Qt naming
        return QSize(320, self._natural_height())

    def _bounds(self) -> tuple[float, float]:
        pad = self.SIDE_PAD * theme.text_scale()
        return pad, max(pad + 10, self.width() - pad)

    def _index_to_x(self, index: int) -> float:
        left, right = self._bounds()
        return left + (right - left) * index / max(1, len(self.steps) - 1)

    def _x_to_index(self, x: float) -> int:
        left, right = self._bounds()
        ratio = min(1.0, max(0.0, (x - left) / max(1.0, right - left)))
        return int(round(ratio * (len(self.steps) - 1)))

    # --- values -------------------------------------------------------------
    @property
    def low(self):
        return self.steps[self._low]

    @property
    def high(self):
        return self.steps[self._high]

    def get(self) -> tuple:
        return self.low, self.high

    def set(self, low, high) -> None:
        self._low = nearest_index(self.steps, low)
        self._high = nearest_index(self.steps, high)
        if self._low > self._high:
            self._low, self._high = self._high, self._low
        self.update()

    # --- painting -----------------------------------------------------------
    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        scale = theme.text_scale()
        mid = self.height() / 2 - 5 * scale
        half = self.TRACK_HEIGHT * scale / 2
        left, right = self._bounds()
        low_x, high_x = self._index_to_x(self._low), self._index_to_x(self._high)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(theme.qcolor("border_strong"))
        painter.drawRoundedRect(QRectF(left, mid - half, right - left, half * 2), half, half)
        painter.setBrush(theme.qcolor("accent"))
        painter.drawRoundedRect(QRectF(low_x, mid - half, max(1.0, high_x - low_x), half * 2),
                                half, half)

        radius = self._radius()
        pen = QPen(theme.qcolor("accent"))
        pen.setWidthF(2 * scale)
        painter.setPen(pen)
        for name, x in (("low", low_x), ("high", high_x)):
            active = self._dragging == name or self._hover == name or (
                self.hasFocus() and name == "low")
            painter.setBrush(theme.qcolor("accent" if active else "bg_input"))
            grow = radius + (1 if active else 0)
            painter.drawEllipse(QRectF(x - grow, mid - grow, grow * 2, grow * 2))

        painter.setPen(theme.qcolor("fg_muted"))
        font = painter.font()
        font.setPixelSize(max(9, int(11 * scale)))
        painter.setFont(font)
        top = self.height() - 16 * scale
        for value, x in ((self.low, low_x), (self.high, high_x)):
            if value == self.high and abs(high_x - low_x) <= 70 * scale:
                break  # the handles are too close for two labels
            text = self.label(value)
            width = painter.fontMetrics().horizontalAdvance(text) + 4
            left_edge = min(max(0.0, x - width / 2), self.width() - width)  # never cut off
            painter.drawText(QRectF(left_edge, top, width, 16 * scale),
                             int(Qt.AlignmentFlag.AlignCenter), text)
        painter.end()

    # --- interaction --------------------------------------------------------
    def _pick(self, x: float) -> str:
        low_x, high_x = self._index_to_x(self._low), self._index_to_x(self._high)
        if abs(x - low_x) == abs(x - high_x):
            return "high" if x > low_x else "low"
        return "low" if abs(x - low_x) < abs(x - high_x) else "high"

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.button() != Qt.MouseButton.LeftButton:
            return
        x = event.position().x()
        self._dragging = self._pick(x)
        self._apply(x)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        x = event.position().x()
        if self._dragging:
            self._apply(x)
            return
        near = self._pick(x)
        hover = near if abs(x - self._index_to_x(
            self._low if near == "low" else self._high)) <= self._radius() * 1.6 else None
        if hover != self._hover:
            self._hover = hover
            self.update()

    def mouseReleaseEvent(self, _event) -> None:  # noqa: N802 - Qt naming
        if self._dragging:
            self._dragging = None
            self.update()
            self.released.emit(self.low, self.high)

    def leaveEvent(self, _event) -> None:  # noqa: N802 - Qt naming
        if self._hover is not None:
            self._hover = None
            self.update()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Arrows move the low handle; with Shift, the high one."""
        step = {Qt.Key.Key_Left: -1, Qt.Key.Key_Down: -1,
                Qt.Key.Key_Right: 1, Qt.Key.Key_Up: 1}.get(event.key())
        if step is None:
            super().keyPressEvent(event)
            return
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self._high = min(len(self.steps) - 1, max(self._high + step, self._low))
        else:
            self._low = max(0, min(self._low + step, self._high))
        self.update()
        self.changed.emit(self.low, self.high)
        self.released.emit(self.low, self.high)

    def _apply(self, x: float) -> None:
        index = self._x_to_index(x)
        if self._dragging == "low":
            self._low = min(index, self._high)
        else:
            self._high = max(index, self._low)
        self.update()
        self.changed.emit(self.low, self.high)
