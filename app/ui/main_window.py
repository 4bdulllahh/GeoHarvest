"""The application shell: sidebar navigation, page stack and status bar.

Pages are built the first time they are opened, so the window appears with one
page in it. Theme, contrast and bold text never rebuild anything: they
re-render the stylesheet string and Qt repaints once.
"""
from __future__ import annotations

import sys
from typing import Callable

from PyQt6.QtCore import QByteArray, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon, QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton,
                             QScrollArea, QSizePolicy, QStackedWidget, QSystemTrayIcon,
                             QVBoxLayout, QWidget)

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
    ("guide", "guide", "Start here", "How it all works", "guide", "GuidePage"),
]
MIN_WIDTH = 760       # the narrowest the window goes (pages stack and wrap to fit)
COMPACT_BELOW = 1000  # narrower than this, the menu shows icons only...
COMPACT_WIDTH = 64    # ...in a sidebar this wide
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

    def set_compact(self, compact: bool) -> None:
        """Icon only (the name shows on hover), for a narrow window."""
        self.title_label.setVisible(not compact)
        self.subtitle_label.setVisible(not compact and theme.text_scale() <= theme.SUBTITLE_MAX_SCALE)
        self.setToolTip(self.title_label.text() if compact else "")

    def set_badge(self, show: bool) -> None:
        self.badge.setText("●" if show else "")
        self.badge.setStyleSheet(
            f"color: {theme.color('warning')}; font-size: {theme.px(9)}px;")


class MainWindow(QMainWindow):
    """The one window. Pages register a builder and are made on first use."""

    theme_changed = pyqtSignal()
    # Relayed from the job running on the Search page, so Leads can update live
    lead_updated = pyqtSignal(int, str, dict)    # search id, place id, new fields
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
        self._update_download = None  # the newest release, while it downloads

        self._build()
        self._size_to_screen()
        self._restore_geometry()
        self._register_pages()
        self.show_page(self._first_page())

        for sequence in (QKeySequence(Qt.Key.Key_F5), QKeySequence("Ctrl+R")):
            QShortcut(sequence, self).activated.connect(self.refresh_app)

        QTimer.singleShot(200, self.refresh_status)
        QTimer.singleShot(20_000, self._auto_backup)  # well after startup, off the UI thread

    def _first_page(self) -> str:
        start = db.get_setting("start_page", None)
        if start is None:  # never chosen: a newcomer starts with the guide
            from app.core import search as searches

            start = "search" if searches.all_searches() else "guide"
        if start == "last":
            start = db.get_setting("last_page", "search")
        return start if start in self._builders else "search"

    def _auto_backup(self) -> None:
        from app.core import backup
        from app.workers.base import Task

        Task(backup.auto_backup).start()  # a failed weekly backup is retried next time

    def tell_user(self, title: str, message: str) -> None:
        """When the user is in another window: a Windows notification and a flashing taskbar
        button, so a long search can run in the background."""
        if self.isActiveWindow() or not prefs.get("notify_done"):
            return
        QApplication.alert(self)
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        tray = getattr(self, "_tray", None)
        if tray is None:
            tray = self._tray = QSystemTrayIcon(self.windowIcon(), self)
            tray.messageClicked.connect(self._bring_to_front)
            tray.activated.connect(lambda _reason: self._bring_to_front())
        tray.show()  # Windows shows notifications from a tray icon; it goes once seen
        tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 10_000)
        QTimer.singleShot(30_000, tray.hide)

    def _bring_to_front(self) -> None:
        self.showNormal() if self.isMinimized() else self.show()
        self.raise_()
        self.activateWindow()

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
        self.setMinimumSize(min(MIN_WIDTH, width), min(560, height))

    # The window opens where it was left, at that size, maximised or not
    def _restore_geometry(self) -> None:
        saved = db.get_setting("window_geometry", "")
        if saved:
            self.restoreGeometry(QByteArray.fromBase64(saved.encode("ascii")))

    def _save_geometry(self) -> None:
        db.set_setting("window_geometry", bytes(self.saveGeometry().toBase64()).decode("ascii"))

    def resizeEvent(self, event):  # noqa: N802 - Qt naming
        super().resizeEvent(event)
        self._fit_sidebar()

    def _fit_sidebar(self) -> None:
        """Below COMPACT_BELOW wide the menu shows icons only, giving the page the room."""
        scale = theme.text_scale()
        compact = self.width() < COMPACT_BELOW * scale
        if getattr(self, "_compact", None) == compact or not hasattr(self, "sidebar"):
            return
        self._compact = compact
        self.sidebar.setFixedWidth(round((COMPACT_WIDTH if compact else theme.SIDEBAR_WIDTH)
                                         * scale))
        self.sidebar_names.setVisible(not compact)
        self.refresh_button.setVisible(not compact)
        for button in self._nav.values():
            button.set_compact(compact)

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
        self.sidebar = sidebar
        self._compact = None

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

        self.sidebar_names = QWidget()
        self.sidebar_names.setProperty("role", "plain")
        names = QVBoxLayout(self.sidebar_names)
        names.setContentsMargins(0, 0, 0, 0)
        names.setSpacing(0)
        title = QLabel(config.APP_TITLE)
        title.setProperty("role", "app-title")
        names.addWidget(title)
        version = QLabel(config.APP_VERSION)
        version.setProperty("role", "hint")
        names.addWidget(version)
        header.addWidget(self.sidebar_names, 1)

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
        self._nav_layout = item_layout
        self.apply_nav_order()
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
        QTimer.singleShot(0, self._fit_sidebar)  # after a rebuild, at the window's real width
        return sidebar

    def apply_nav_order(self) -> None:
        """Put the sidebar pages in the user's order and hide the ones switched off."""
        order = prefs.ordered([item[0] for item in NAV_ITEMS], prefs.get("nav_order"))
        hidden = prefs.hidden_pages()
        for index, key in enumerate(order):
            button = self._nav[key]
            self._nav_layout.removeWidget(button)
            self._nav_layout.insertWidget(index, button)
            button.setVisible(key not in hidden)

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
        db.set_setting_soft("last_page", key)
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
        if not self.busy_page_reason():  # while a search runs, the Search page owns this text
            mode = db.get_setting("ai_provider", "")
            self.status_left.setText(t("Smart mode ready") if mode else t("Quick mode"))

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
        self.show_theme(lambda: theme.set_appearance(mode))

    def show_theme(self, choose: Callable[[], None], font: str | None = None) -> None:
        """Switch theme. A new font changes widths as well as colours, so that rebuilds.

        ``font`` is the font before the change, when the change was already previewed.
        """
        font = font or theme.ui_family()
        choose()
        if theme.ui_family() != font and not self.busy_page_reason():
            self._rebuild()
        else:
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
        self._rebuild()

    def _rebuild(self) -> None:
        """Throw away the window's contents and build them again on the same page: for
        changes to sizes and fonts, which restyling alone can't apply."""
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

    # --- updates ------------------------------------------------------------
    # Every start: ask GitHub for the newest release, download it in the background and
    # install it (the app closes and reopens) as soon as no search is running. Always the
    # newest release, never one version after another (user's choice, 0.3).
    def check_for_update_soon(self, delay_ms: int = 2500) -> None:
        """Ask GitHub for a newer release once the window is up. Silent when offline."""
        QTimer.singleShot(delay_ms, self.check_for_update)

    def check_for_update(self, tell_if_none: bool = False) -> None:
        from app.services import updater
        from app.workers.base import Task

        if self._update_download is not None:
            if tell_if_none:
                toast(self, t("The new version is downloading; it installs when it's done."))
            return

        def result(release) -> None:
            if release is None:
                if tell_if_none:
                    toast(self, t("You have the latest version ({version}).",
                                  version=config.APP_VERSION), "success")
            elif updater.can_update_itself(release):
                self._download_update(release)
            elif not getattr(sys, "frozen", False) or tell_if_none:
                # From source, or GitHub is still attaching the download: say so only
                toast(self, t("GeoHarvest {tag} is out. Get it from the GitHub page.",
                              tag=release.tag), "info", 8000)

        Task(updater.available_update).start(on_result=result)

    def _download_update(self, release) -> None:
        from app.ui.widgets.update_dialog import UpdateDownloadWorker

        worker = UpdateDownloadWorker(release)
        self._update_download = worker
        tag = release.tag

        def progress(received: int, total: int, _detail: str) -> None:
            if total:
                self.set_status(middle=t("Downloading GeoHarvest {tag}: {percent}%", tag=tag,
                                         percent=received * 100 // total))

        def failed(message: str) -> None:
            self._update_download = None
            self.set_status(middle="")
            toast(self, t("The update to {tag} didn't download ({message}). GeoHarvest tries "
                          "again next time it opens.", tag=tag, message=message), "warn", 8000)

        def downloaded(setup) -> None:
            self._update_download = None
            self.set_status(middle="")
            self._install_update(release, setup)

        worker.signals.progress.connect(progress)
        worker.signals.failed.connect(failed)
        worker.signals.finished.connect(downloaded)
        worker.start()

    def _install_update(self, release, setup) -> None:
        """Install now, unless a search is running or a question is open: then wait."""
        if self.busy_page_reason() or QApplication.activeModalWidget() is not None:
            self.set_status(middle=t("GeoHarvest {tag} is ready: it installs when the search "
                                     "ends.", tag=release.tag))
            QTimer.singleShot(15000, lambda: self._install_update(release, setup))
            return
        from app.ui.widgets.update_dialog import UpdatingNotice

        UpdatingNotice(self, release, setup).exec()

    def quit_app(self) -> None:
        """Close without questions (the updater is waiting for us to exit)."""
        self._save_geometry()
        for page in self._pages.values():
            stop = getattr(page, "stop", None)
            if callable(stop):
                stop()
        from app.workers import base as workers

        workers.shutdown(2000)
        db.close()
        QApplication.quit()

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

        self._save_geometry()
        from app.workers import base as workers

        workers.shutdown(2000)
        db.close()
        event.accept()
