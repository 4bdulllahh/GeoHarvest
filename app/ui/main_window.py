"""The application shell: sidebar navigation, page stack and status bar.

Pages are built the first time they are opened, so the window appears with one
page in it. Theme, contrast and bold text never rebuild anything: they
re-render the stylesheet string and Qt repaints once.
"""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon, QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton,
                             QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget)

from app import config
from app.core import db, prefs
from app.i18n import t
from app.ui import theme
from app.ui.widgets.common import restyle, separator, toast

# (key, icon, title, subtitle, module, class)
NAV_ITEMS = [
    ("search", "search", "New search", "Find businesses", "search", "SearchPage"),
    ("leads", "leads", "Leads", "Everything found", "leads", "LeadsPage"),
    ("history", "history", "Past searches", "Reopen or resume", "history", "HistoryPage"),
    ("smart", "smart", "Smart mode", "AI checks each lead", "smart", "SmartPage"),
]
SETTINGS_ITEM = ("settings", "settings", "Settings", "Theme, speed, updates", "settings",
                 "SettingsPage")


class NavButton(QPushButton):
    """One menu entry: icon, title, hint and an optional attention dot."""

    def __init__(self, key: str, icon_name: str, title: str, subtitle: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("nav", "off")

        scale = theme.text_scale()
        show_subtitle = scale <= theme.SUBTITLE_MAX_SCALE
        # Height via size hints, not setFixedHeight: re-polishing on a stylesheet
        # change replaces size constraints set in code with the stylesheet's.
        self._height = theme.nav_height()
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(round(10 * scale), round(9 * scale), round(10 * scale),
                                  round(9 * scale))
        layout.setSpacing(round(11 * scale))

        self.icon_label = QLabel(theme.icon(icon_name))
        self.icon_label.setFixedWidth(round(20 * scale))
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon_label)

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(round(3 * scale))
        self.title_label = QLabel(t(title))
        text.addWidget(self.title_label)
        # Parented from the outset: a parentless visible QLabel is a top-level window
        self.subtitle_label = QLabel(t(subtitle), self)
        self.subtitle_label.setProperty("role", "hint")
        if show_subtitle:
            text.addWidget(self.subtitle_label)
        else:
            self.subtitle_label.hide()
        layout.addLayout(text, 1)

        self.badge = QLabel("")
        self.badge.setFixedWidth(round(12 * scale))
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.badge)

        self.set_active(False)

    def set_active(self, active: bool) -> None:
        self.setProperty("nav", "on" if active else "off")
        restyle(self)
        family = theme.icon_family()
        self.icon_label.setStyleSheet(
            (f'font-family: "{family}"; ' if family else "")
            + f"font-size: {theme.px(17)}px; "
            + f"color: {theme.color('accent') if active else theme.color('fg_muted')};")
        self.title_label.setStyleSheet(
            f"font-size: {theme.px(13)}px; "
            f"font-weight: {'700' if (active or theme.bold_text()) else '600'}; "
            f"color: {theme.color('accent') if active else theme.color('fg')};")

    def sizeHint(self):  # noqa: N802 - Qt naming
        hint = super().sizeHint()
        hint.setHeight(self._height)
        return hint

    def minimumSizeHint(self):  # noqa: N802 - Qt naming
        hint = super().minimumSizeHint()
        hint.setHeight(self._height)
        return hint

    def set_badge(self, show: bool) -> None:
        self.badge.setText("●" if show else "")
        self.badge.setStyleSheet(
            f"color: {theme.color('warning')}; font-size: {theme.px(9)}px;")


class MainWindow(QMainWindow):
    """The one window. Pages register a builder and are made on first use."""

    theme_changed = pyqtSignal()
    # Relayed from the job running on the Search page, so Leads can update live
    leads_added = pyqtSignal(int, list)          # search id, new leads
    lead_updated = pyqtSignal(int, str, dict)    # search id, place id, new fields
    lead_removed = pyqtSignal(int, str)          # search id, place id
    search_finished = pyqtSignal(int)            # search id

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{config.APP_TITLE} {config.APP_VERSION}  ·  {t(config.APP_TAGLINE)}")
        path = config.resource_path("assets/icon.ico")
        if path.exists():
            self.setWindowIcon(QIcon(str(path)))

        self._builders: dict[str, Callable[[], QWidget]] = {}
        self._pages: dict[str, QWidget] = {}
        self._nav: dict[str, NavButton] = {}
        self.current: str | None = None

        self._build()
        self._size_to_screen()
        self._register_pages()
        self.show_page("search")

        for sequence in (QKeySequence(Qt.Key.Key_F5), QKeySequence("Ctrl+R")):
            QShortcut(sequence, self).activated.connect(self.refresh_app)

        QTimer.singleShot(200, self.refresh_status)

    # --- chrome -------------------------------------------------------------
    def showEvent(self, event):  # noqa: N802 - Qt naming
        super().showEvent(event)
        if not getattr(self, "_taskbar_icon_kept", False):
            self._taskbar_icon_kept = True
            from app.ui import taskbar

            taskbar.keep_icon(self)

    def _size_to_screen(self) -> None:
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else None
        width = min(1360, (available.width() - 80) if available else 1360)
        height = min(880, (available.height() - 60) if available else 880)
        self.resize(width, height)
        self.setMinimumSize(min(1000, width), min(620, height))

    def _build(self) -> None:
        central = QWidget()
        central.setProperty("role", "plain")
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_sidebar())

        self.stack = QStackedWidget()
        self.stack.setProperty("role", "plain")
        body.addWidget(self.stack, 1)
        outer.addLayout(body, 1)

        outer.addWidget(self._build_status_bar())
        self.setCentralWidget(central)

    def _build_sidebar(self) -> QWidget:
        scale = theme.text_scale()
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(round(theme.SIDEBAR_WIDTH * scale))

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(round(10 * scale), round(14 * scale), round(10 * scale),
                                  round(10 * scale))
        layout.setSpacing(round(4 * scale))

        header = QHBoxLayout()
        header.setSpacing(round(10 * scale))
        logo = QLabel()
        size = round(40 * scale)
        pixmap = QPixmap(str(config.resource_path("assets/logo-96.png")))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation))
        logo.setFixedSize(QSize(size, size))
        header.addWidget(logo)

        names = QVBoxLayout()
        names.setSpacing(0)
        title = QLabel(config.APP_TITLE)
        title.setProperty("role", "app-title")
        names.addWidget(title)
        version = QLabel(config.APP_VERSION)
        version.setProperty("role", "hint")
        names.addWidget(version)
        header.addLayout(names, 1)

        # Rebuilds the page on screen: the fix a user can reach for without restarting
        self.refresh_button = QPushButton(theme.icon("refresh"))
        self.refresh_button.setProperty("kind", "ghost")
        self.refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_button.setFixedSize(QSize(round(30 * scale), round(30 * scale)))
        self.refresh_button.setToolTip(t("Refresh this page (F5)"))
        self.refresh_button.clicked.connect(self.refresh_app)
        header.addWidget(self.refresh_button, 0, Qt.AlignmentFlag.AlignTop)
        self._paint_refresh_button()

        layout.addLayout(header)
        layout.addSpacing(round(8 * scale))
        layout.addWidget(separator())
        layout.addSpacing(round(6 * scale))

        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        scroller.setFrameShape(QFrame.Shape.NoFrame)
        scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroller.viewport().setAutoFillBackground(False)

        items = QWidget()
        items.setProperty("role", "plain")
        item_layout = QVBoxLayout(items)
        item_layout.setContentsMargins(0, 0, 0, 0)
        item_layout.setSpacing(round(6 * scale))
        for key, icon_name, label, subtitle, _module, _cls in NAV_ITEMS:
            button = NavButton(key, icon_name, label, subtitle)
            button.clicked.connect(lambda _checked=False, k=key: self.show_page(k))
            item_layout.addWidget(button)
            self._nav[key] = button
        item_layout.addStretch(1)
        scroller.setWidget(items)
        layout.addWidget(scroller, 1)

        layout.addSpacing(round(6 * scale))
        layout.addWidget(separator())
        layout.addSpacing(round(6 * scale))
        key, icon_name, label, subtitle, _module, _cls = SETTINGS_ITEM
        settings = NavButton(key, icon_name, label, subtitle)
        settings.clicked.connect(lambda _checked=False: self.show_page("settings"))
        layout.addWidget(settings)
        self._nav[key] = settings
        return sidebar

    def _paint_refresh_button(self) -> None:
        family = theme.icon_family()
        self.refresh_button.setStyleSheet(
            (f'font-family: "{family}"; ' if family else "")
            + f"font-size: {theme.px(16)}px; border: none; padding: 0; "
            + f"color: {theme.color('fg_muted')};")

    def _build_status_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("StatusBar")
        bar.setFixedHeight(round(26 * theme.text_scale()))
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(16)
        self.status_left = QLabel("")
        self.status_middle = QLabel("")
        self.status_right = QLabel("")
        layout.addWidget(self.status_left)
        layout.addStretch(1)
        layout.addWidget(self.status_middle)
        layout.addWidget(self.status_right)
        return bar

    # --- pages --------------------------------------------------------------
    def _register_pages(self) -> None:
        """Record how to build each page. Nothing is constructed until it is shown."""

        def builder(module_name: str, class_name: str) -> Callable[[], QWidget]:
            def make() -> QWidget:
                import importlib

                module = importlib.import_module(f"app.ui.pages.{module_name}")
                return getattr(module, class_name)(self)

            return make

        for key, _icon, _title, _sub, module, cls in NAV_ITEMS + [SETTINGS_ITEM]:
            self._builders[key] = builder(module, cls)

    def page(self, key: str) -> QWidget | None:
        """The page if it has been opened, else None. Never builds one."""
        return self._pages.get(key)

    def ensure_page(self, key: str) -> QWidget | None:
        if key in self._pages:
            return self._pages[key]
        builder = self._builders.get(key)
        if builder is None:
            return None
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            page = builder()
        finally:
            QApplication.restoreOverrideCursor()
        self._pages[key] = page
        self.stack.addWidget(page)
        return page

    def show_page(self, key: str) -> None:
        page = self.ensure_page(key)
        if page is None:
            return
        if self.current in self._nav:
            self._nav[self.current].set_active(False)
        self.current = key
        self._nav[key].set_active(True)
        self.stack.setCurrentWidget(page)
        on_show = getattr(page, "on_show", None)
        if callable(on_show):
            try:
                on_show()
            except Exception as error:  # noqa: BLE001 - a broken page must not break navigation
                toast(self, t("Could not refresh this page: {error}", error=error), "error")
        self.refresh_status()

    def refresh_app(self) -> None:
        """Reload the page on screen, like F5 in a browser.

        A page with a worker still running is re-read in place instead: destroying
        it would leave that worker calling back into deleted widgets.
        """
        current = self.current
        if current is None:
            return
        page = self._pages.get(current)
        reason = page.busy_reason() if page is not None and hasattr(page, "busy_reason") else None
        if reason:
            on_show = getattr(page, "on_show", None)
            if callable(on_show):
                on_show()
            toast(self, t("Reloaded what is on screen. Left the page alone because {reason}.",
                          reason=reason), "info", 5000)
            return
        self.setUpdatesEnabled(False)
        try:
            if page is not None:
                self._pages.pop(current, None)
                self.stack.removeWidget(page)
                page.deleteLater()
            self.current = None
            self.show_page(current)
        finally:
            self.setUpdatesEnabled(True)
        toast(self, "Refreshed", "success", 2000)

    def notify(self, message: str, level: str = "info", duration: int = 4000) -> None:
        toast(self, message, level, duration)

    # --- status -------------------------------------------------------------
    def set_status(self, left: str | None = None, middle: str | None = None) -> None:
        """Pages report what is going on (a scrape running, say) through here."""
        if left is not None:
            self.status_left.setText(left)
        if middle is not None:
            self.status_middle.setText(middle)

    def refresh_status(self) -> None:
        row = db.query_one("SELECT COUNT(*) AS n FROM leads")
        self.status_right.setText(t("{count:,} leads saved", count=row["n"] if row else 0))
        if not self.status_left.text():
            mode = db.get_setting("ai_provider", "")
            self.status_left.setText(t("Smart mode on") if mode else t("Quick mode"))

    # --- appearance ---------------------------------------------------------
    def apply_theme(self) -> None:
        """Repaint the whole app from the current tokens. No widget is rebuilt."""
        app = QApplication.instance()
        self.setUpdatesEnabled(False)
        try:
            if app is not None:
                app.setStyleSheet(theme.stylesheet())
            for key, button in self._nav.items():
                button.set_active(key == self.current)
                button.set_badge(bool(button.badge.text()))
            self._paint_refresh_button()
            for widget in self.findChildren(QWidget):
                refresh = getattr(widget, "refresh_theme", None)
                if callable(refresh):
                    try:
                        refresh()
                    except Exception:  # noqa: BLE001
                        pass
        finally:
            self.setUpdatesEnabled(True)
        self.theme_changed.emit()

    def change_appearance(self, mode: str) -> None:
        db.set_setting("appearance", mode)
        theme.set_appearance(mode)
        self.apply_theme()

    def change_contrast(self, enabled: bool) -> None:
        db.set_setting("high_contrast", enabled)
        theme.set_high_contrast(enabled)
        self.apply_theme()

    def change_bold_text(self, enabled: bool) -> None:
        db.set_setting("bold_text", enabled)
        theme.set_bold_text(enabled)
        self.apply_theme()

    def change_text_size(self, key: str) -> None:
        """Text size changes metrics, so built pages are discarded and rebuilt."""
        db.set_setting("text_size", key)
        theme.set_text_scale(prefs.text_scale())
        reason = self.busy_page_reason()
        if reason:
            self.apply_theme()
            toast(self, t("Text size applies fully once {reason} has finished.", reason=reason),
                  "warn", 6000)
            return
        current = self.current or "search"
        self.setUpdatesEnabled(False)
        try:
            for page in self._pages.values():
                self.stack.removeWidget(page)
                page.deleteLater()
            self._pages.clear()
            self.current = None
            old = self.centralWidget()
            self._nav.clear()
            self._build()
            if old is not None:
                old.deleteLater()
            self.apply_theme()
            self.show_page(current)
        finally:
            self.setUpdatesEnabled(True)

    # --- lifecycle ----------------------------------------------------------
    def busy_page_reason(self) -> str | None:
        """The first reason any built page gives for not being torn down."""
        for page in self._pages.values():
            ask = getattr(page, "busy_reason", None)
            reason = ask() if callable(ask) else None
            if reason:
                return reason
        return None

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        reason = self.busy_page_reason()
        if reason:
            from app.ui.widgets.dialogs import ConfirmDialog

            if not ConfirmDialog.ask(
                self, "A search is still running",
                "Closing now stops it. Every lead found so far is saved, and you can resume "
                "the search from Past searches next time.\n\nClose anyway?",
                confirm_text="Close and stop", danger=True,
            ):
                event.ignore()
                return
            for page in self._pages.values():
                stop = getattr(page, "stop", None)
                if callable(stop):
                    stop()

        from app.workers import base as workers

        workers.shutdown(2000)
        db.close()
        event.accept()
