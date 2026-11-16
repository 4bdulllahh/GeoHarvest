"""Downloading the newest release, and the notice shown just before it installs."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QTextBrowser, QVBoxLayout, QWidget

from app import config
from app.i18n import t
from app.services import updater
from app.ui import theme
from app.ui.widgets.common import confirm_button, secondary_button, set_tone
from app.workers.base import Worker


class UpdateDownloadWorker(Worker):
    """Download and unpack a release. Finishes with the folder of new app files."""

    def __init__(self, release: updater.Release):
        super().__init__()
        self.release = release

    def work(self) -> Path:
        try:
            return updater.download(self.release, lambda got, total: self.report(got, total),
                                    lambda: self.cancelled)
        except updater.UpdateCancelled:
            return Path()


class UpdatingNotice(QDialog):
    """The newest release is downloaded: ask "Update now" or "Later". Update now hands over
    to Setup, which closes the app, installs and opens it again. Later (also Escape and the
    window's X) only closes this: the next start downloads and asks again."""

    def __init__(self, window: QWidget, release: updater.Release, setup: Path):
        super().__init__(window)
        self.window_ = window
        self.setup = setup
        scale = theme.text_scale()
        self.setWindowTitle(t("Update GeoHarvest"))
        self.setModal(True)
        self.setMinimumWidth(round(520 * scale))
        pad = round(22 * scale)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(pad, pad, pad, pad)
        layout.setSpacing(round(12 * scale))

        heading = QLabel(t("GeoHarvest {tag} is ready to install", tag=release.tag))
        heading.setProperty("role", "subheading")
        heading.setWordWrap(True)
        layout.addWidget(heading)
        message = QLabel(t("You have {app_version}. With \"Update now\", GeoHarvest closes, "
                           "installs the new version and opens again by itself in about 10 "
                           "seconds. With \"Later\", it asks again the next time it opens. Your "
                           "searches, leads and settings are kept.",
                           app_version=config.APP_VERSION))
        message.setWordWrap(True)
        layout.addWidget(message)
        if release.notes.strip():
            label = QLabel(t("What's new"))
            label.setProperty("role", "field")
            layout.addWidget(label)
            notes = QTextBrowser()
            notes.setOpenExternalLinks(True)
            notes.setMarkdown(release.notes)
            notes.setMaximumHeight(round(220 * scale))
            layout.addWidget(notes)
        self.status = QLabel("")
        self.status.setProperty("role", "muted")
        self.status.setWordWrap(True)
        self.status.setVisible(False)
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.later_button = secondary_button("Later", self.reject)
        buttons.addWidget(self.later_button)
        self.now_button = confirm_button("Update now", self._install, width=200)
        self.now_button.setDefault(True)
        buttons.addWidget(self.now_button)
        layout.addLayout(buttons)

    def _install(self) -> None:
        if not self.now_button.isEnabled():
            return
        self.now_button.setEnabled(False)
        try:
            updater.start_install(self.setup)
        except OSError as error:
            self.status.setText(t("The update didn't start: {message}. GeoHarvest tries again "
                                  "next time it opens.", message=str(error)))
            set_tone(self.status, "error")
            self.status.setVisible(True)
            QTimer.singleShot(6000, self.accept)
            return
        self.accept()
        self.window_.quit_app()  # Setup waits for the app to close
