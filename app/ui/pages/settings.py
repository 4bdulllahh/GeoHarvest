"""Settings: appearance, search speed, updates and the user's data."""
from __future__ import annotations

import os
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app import config
from PyQt6 import sip
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QAbstractItemView, QFileDialog, QListWidget, QListWidgetItem,
                             QVBoxLayout, QWidget)

from app.core import backup, credentials, db, prefs, scraper, themes
from app.i18n import t
from app.services import updater
from app.ui import scrolling, theme
from app.ui.pages.base import Page
from app.ui.widgets.common import (ChoiceButtons, FormRow, Section, danger_button, hint, muted,
                                   open_url, primary_button, row, secondary_button, wrap_row)
from app.ui.widgets.dialogs import ChoiceDialog, ConfirmDialog
from app.ui.widgets.inputs import checkbox, text_box
from app.workers.base import Task

SPEEDS = [("2", "Gentle"), ("4", "Normal"), ("8", "Fast")]


class SettingsPage(Page):
    def __init__(self, window):
        super().__init__(window)
        self.add_header("Settings", "How GeoHarvest looks and behaves.")
        body = self.scroll_body()
        layout = body.body_layout

        layout.addWidget(self._language_section())
        layout.addWidget(self._appearance_section())
        layout.addWidget(self._everyday_section())

        speed = Section("Search speed",
                        "How many cities GeoHarvest searches at the same time.")
        speed.add(ChoiceButtons(SPEEDS, str(db.get_setting("parallel_searches", 4)),
                                on_change=lambda v: db.set_setting("parallel_searches", int(v))))
        speed.add(hint("Fast finishes big searches sooner, but Google is more likely to ask "
                       "GeoHarvest to slow down. If that happens, the search pauses and you can "
                       "resume it later from Past searches. Applies to the next search."))
        layout.addWidget(speed)

        proxies = Section("Proxies (optional)",
                          "For people who search a lot. GeoHarvest sends its Google Maps "
                          "searches through these, taking turns, and skips any that stop working "
                          "or that Google slows down. Website visits and AI go direct.")
        self.proxies = text_box("One per line, for example:\n1.2.3.4:8080\n"
                                "user:password@1.2.3.4:8080\n1.2.3.4:8080:user:password\n"
                                "socks5://1.2.3.4:1080", monospace=True, lines=6)
        self.proxies.setPlainText(credentials.load_secret(scraper.PROXIES_SECRET))
        proxies.add(self.proxies)
        self.proxy_status = hint("")
        self.test_button = secondary_button("Test them", self.test_proxies)
        proxies.add(row(secondary_button("Save", self.save_proxies), self.test_button,
                        self.proxy_status, stretch=2))
        proxies.add(hint("Kept encrypted on this computer, since proxies often include a "
                         "password. Leave the box empty to search without proxies. Applies to "
                         "the next search."))
        layout.addWidget(proxies)

        updates = Section("Updates", t("You have GeoHarvest {version}. Each time it opens, "
                                       "GeoHarvest checks for a newer version and installs it "
                                       "by itself, waiting while a search runs.",
                                       version=config.APP_VERSION))
        updates.add(row(secondary_button("Check now",
                                         lambda: window.check_for_update(tell_if_none=True)),
                        secondary_button("Open the GitHub page",
                                         lambda: open_url(config.REPO_URL)), None))
        layout.addWidget(updates)

        layout.addWidget(self._data_section())

        if updater.uninstaller():
            remove = Section("Uninstall", "Remove GeoHarvest from this computer.")
            remove.add(row(danger_button("Uninstall GeoHarvest...", self.uninstall), None))
            layout.addWidget(remove)

        fair = Section("Use it fairly")
        fair.add(muted("GeoHarvest reads public Google Maps listings and business websites. "
                       "When you contact the businesses you find, follow the rules where you "
                       "and they are, such as GDPR in the EU and UK, CAN-SPAM in the US and the "
                       "UAE's data protection law, and Google's terms of service."))
        layout.addWidget(fair)

        about = Section("About")
        about.add(muted(t("GeoHarvest {app_version}, © 2026 Abdullah. Free software: "
                          "GeoHarvest's code is MIT licensed, and this download, which "
                          "includes PyQt6, is distributed under the GNU GPL v3. It comes "
                          "with no warranty. Not affiliated with Google.",
                          app_version=config.APP_VERSION)))
        about.add(wrap_row(
            secondary_button("Report a problem or suggest an idea",
                             lambda: open_url(f"{config.REPO_URL}/issues/new")),
            secondary_button("Open the licenses", self.open_licenses),
            secondary_button("Source code", lambda: open_url(config.REPO_URL))))
        layout.addWidget(about)
        layout.addStretch(1)

    # --- language ------------------------------------------------------------
    def _language_section(self) -> Section:
        """Each language is shown in its own words, so anyone can find theirs."""
        from app import i18n

        section = Section("Language", "Changes every page, button and message straight away. "
                                      "Arabic also turns the layout to read from right to "
                                      "left. Business details from Google stay as Google "
                                      "wrote them, and the columns in exported files stay in "
                                      "English, so CRMs can read them.")
        section.add(ChoiceButtons([(code, native) for code, native, _english in i18n.LANGUAGES],
                                  i18n.language(), on_change=self.window_.change_language))
        return section

    # --- everyday ------------------------------------------------------------
    def _everyday_section(self) -> Section:
        section = Section("Everyday use")
        start = FormRow("First page when GeoHarvest opens")
        start.add(ChoiceButtons(prefs.START_PAGES, prefs.get("start_page"),
                                on_change=lambda key: db.set_setting("start_page", key)))
        section.add(start)
        dates = FormRow("Dates", "How dates look in the lists. Excel files keep the full date.")
        dates.add(ChoiceButtons([(key, label) for key, (label, _) in prefs.DATE_FORMATS.items()],
                                prefs.get("date_format"),
                                on_change=lambda key: db.set_setting("date_format", key)))
        section.add(dates)
        times = FormRow("Times")
        times.add(ChoiceButtons(list(prefs.TIME_FORMATS.items()), prefs.get("time_format"),
                                on_change=lambda key: db.set_setting("time_format", key)))
        section.add(times)
        tell = FormRow("When a search finishes", "Only while you are in another window, so a "
                                                 "long search can run in the background.")
        tell.add(checkbox("Show a Windows notification and flash the taskbar button",
                          bool(prefs.get("notify_done")),
                          on_change=lambda on: db.set_setting("notify_done", bool(on))))
        section.add(tell)
        return section

    # --- your data ------------------------------------------------------------
    def _data_section(self) -> Section:
        data = Section("Your data",
                       "Searches, leads, presets, settings and your encrypted AI key are kept on "
                       "this computer only, in your user folder. Updating GeoHarvest never "
                       "touches them.")
        saves = FormRow("Backups", "A backup holds your searches, leads, presets and settings, "
                                   "to keep somewhere safe or move to another computer. Your AI "
                                   "key and proxies aren't in it: they are encrypted for this "
                                   "Windows account only, so you type them in again there.")
        saves.add(wrap_row(primary_button("Back up...", self._backup),
                           secondary_button("Restore from a backup...", self._restore),
                           secondary_button("Open the backups folder", self._open_backups)))
        saves.add(checkbox("Back up by itself once a week (keeps the last 4)",
                           bool(db.get_setting("auto_backup", True)),
                           on_change=lambda on: db.set_setting("auto_backup", bool(on))))
        last = backup.last_backup()
        saves.add(hint(t("Last backup: {when}", when=prefs.format_datetime(last)) if last
                       else t("No backup yet.")))
        data.add(saves)
        data.add(wrap_row(
            secondary_button("Open the data folder",
                             lambda: os.startfile(config.DATA_DIR)),  # noqa: S606
            secondary_button("Forget saved keys...", self._forget_keys),
            danger_button("Delete all searches and leads...", self.delete_all)))
        return data

    def _backup(self) -> None:
        target, _filter = QFileDialog.getSaveFileName(
            self, t("Save a backup of GeoHarvest"),
            str(Path.home() / "Documents" / backup.default_name()),
            t("GeoHarvest backup (*.ghbackup)"))
        if not target:
            return

        def done(path: Path) -> None:
            db.set_setting("last_backup", db.now())
            self.notify(t("Backup saved: {name}", name=path.name), "success", 6000)

        Task(backup.write_backup, target).start(
            on_result=self.guard(done),
            on_error=self.guard(lambda message: self.notify(
                t("The backup couldn't be saved: {message}", message=message), "error", 8000)))

    def _open_backups(self) -> None:
        backup.folder().mkdir(parents=True, exist_ok=True)
        os.startfile(backup.folder())  # noqa: S606

    def _restore(self) -> None:
        reason = self.window_.busy_page_reason()
        if reason:
            self.notify(t("Wait until {reason} has finished, then restore.", reason=reason),
                        "warn", 6000)
            return
        source, _filter = QFileDialog.getOpenFileName(
            self, t("Choose a GeoHarvest backup"), str(backup.folder()),
            t("GeoHarvest backup (*.ghbackup);;All files (*.*)"))
        if not source:
            return
        if not backup.is_backup(source):
            self.notify("That file isn't a GeoHarvest backup.", "error", 6000)
            return
        if not ConfirmDialog.ask(
                self, "Restore this backup?",
                "Everything in GeoHarvest is replaced with what is in the backup: searches, "
                "leads, presets and settings. What is there now is saved as a backup first, in "
                "the backups folder, so you can go back.", "Restore", danger=True):
            return
        try:
            backup.restore_backup(source)
        except (OSError, sqlite3.Error) as error:
            self.notify(t("The backup couldn't be restored: {error}", error=error), "error", 8000)
            return
        window = self.window_
        theme.apply_preferences()  # the backup's theme, text size and menu
        scrolling.set_smooth(bool(prefs.get("smooth_scroll")))
        window._rebuild()  # this page goes too: nothing below may touch self
        window.apply_nav_order()
        window.refresh_status()
        window.notify("Backup restored.", "success", 6000)

    def _forget_keys(self) -> None:
        if not ConfirmDialog.ask(
                self, "Forget saved keys?",
                "Your AI keys (for every AI) and your proxies are deleted from this computer. "
                "Smart mode needs a key again before it can score leads.", "Forget them",
                danger=True):
            return
        credentials.clear_all()
        self.proxies.clear()
        smart = self.window_.page("smart")
        if smart is not None:
            smart.key.clear()
        self.notify("Saved keys and proxies forgotten.", "success")

    # --- appearance (from HomingPigeon) --------------------------------------
    def _appearance_section(self) -> Section:
        look = Section("Appearance")
        theme_row = FormRow("Theme", "Pick a ready-made theme, or make your own with your "
                                     "colours, a gradient and a font.")
        self.theme_holder = QWidget()
        self.theme_holder.setProperty("role", "plain")
        QVBoxLayout(self.theme_holder).setContentsMargins(0, 0, 0, 0)
        theme_row.add(self.theme_holder)
        self.edit_theme_button = secondary_button("Change this theme...", self._edit_theme)
        self.delete_theme_button = danger_button("Delete this theme", self._delete_theme)
        self.share_theme_button = secondary_button("Save theme to a file...", self._share_theme)
        self.share_theme_button.setToolTip(t("Give your theme to someone else"))
        theme_row.add(wrap_row(
            primary_button("Make my own theme...", self._new_theme), self.edit_theme_button,
            self.delete_theme_button, self.share_theme_button,
            secondary_button("Load a theme from a file...", self._load_theme)))
        look.add(theme_row)
        self._fill_themes()

        size_row = FormRow("Text size", "Makes everything bigger: text, buttons and boxes.")
        size_row.add(ChoiceButtons([(k, label) for k, label, _ in prefs.TEXT_SIZES],
                                   prefs.get("text_size"), on_change=self.window_.change_text_size))
        look.add(size_row)
        reading = FormRow("Easier to read", "High contrast uses stronger colours for text and "
                                            "borders. Bold text makes all writing heavier. "
                                            "Smooth scrolling makes pages glide on the mouse "
                                            "wheel; switch it off if scrolling feels slow.")
        reading.add(checkbox("High contrast", bool(prefs.get("high_contrast")),
                             on_change=self.window_.change_contrast))
        reading.add(checkbox("Bold text", bool(prefs.get("bold_text")),
                             on_change=self.window_.change_bold_text))
        reading.add(checkbox("Smooth scrolling", bool(prefs.get("smooth_scroll")),
                             on_change=self._smooth_changed))
        look.add(reading)

        menu_row = FormRow("Menu on the left", "Drag the pages into the order you like. Switch off "
                                               "a page you never use to hide it. New search is "
                                               "always shown.")
        self.menu_list = QListWidget()
        self.menu_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.menu_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.menu_list.setMaximumWidth(round(420 * theme.text_scale()))
        self._fill_menu_list()
        self.menu_list.model().rowsMoved.connect(lambda *_args: self._menu_changed())
        self.menu_list.itemChanged.connect(lambda _item: self._menu_changed())
        menu_row.add(self.menu_list)
        menu_row.add(row(secondary_button("Put the menu back the way it was",
                                          self._reset_menu), None))
        look.add(menu_row)

        reset_row = FormRow("Start over", "Put the theme, text size, reading options and menu "
                                          "back to how they were when you installed the app. "
                                          "Themes you made are kept.")
        reset_row.add(row(secondary_button("Reset appearance settings",
                                           self._reset_appearance), None))
        look.add(reset_row)
        return look

    def _fill_themes(self) -> None:
        layout = self.theme_holder.layout()
        while layout.count():
            layout.takeAt(0).widget().deleteLater()
        options = list(prefs.THEMES) + [(key, spec["name"])
                                        for key, spec in themes.PRESETS.items()]
        options += [(themes.custom_key(spec["name"]), spec["name"])
                    for spec in themes.custom_themes()]
        self.theme_choice = ChoiceButtons(options, prefs.get("appearance"),
                                          on_change=self._choose_theme)
        layout.addWidget(self.theme_choice)
        self._paint_theme_buttons()

    def _paint_theme_buttons(self) -> None:
        mine = str(prefs.get("appearance")).startswith(themes.CUSTOM_PREFIX)
        self.edit_theme_button.setEnabled(mine)
        self.delete_theme_button.setEnabled(mine)
        self.share_theme_button.setEnabled(themes.find(prefs.get("appearance")) is not None)

    def _choose_theme(self, key: str) -> None:
        self.window_.change_appearance(key)
        if not sip.isdeleted(self):  # a font change rebuilds the window, this page too
            self._paint_theme_buttons()

    def _new_theme(self) -> None:
        from app.ui.widgets.theme_editor import ThemeEditor

        ThemeEditor(self.window_, on_saved=lambda _key: self._fill_themes()).exec()

    def _edit_theme(self) -> None:
        from app.ui.widgets.theme_editor import ThemeEditor

        spec = themes.find(prefs.get("appearance"))
        if spec is not None:
            ThemeEditor(self.window_, spec, on_saved=lambda _key: self._fill_themes()).exec()

    def _delete_theme(self) -> None:
        spec = themes.find(prefs.get("appearance"))
        if spec is None or not ConfirmDialog.ask(
                self, "Delete this theme?",
                t("Delete {name}? The app goes back to the Dark theme.", name=spec["name"]),
                "Delete", danger=True):
            return
        themes.delete_custom(spec["name"])
        db.set_setting("appearance", "Dark")
        self._fill_themes()
        self._choose_theme("Dark")

    def _share_theme(self) -> None:
        spec = themes.find(prefs.get("appearance"))
        if spec is None:
            return
        path, _filter = QFileDialog.getSaveFileName(
            self, t("Save theme to a file"), t(spec["name"]) + themes.FILE_SUFFIX,
            t("GeoHarvest theme (*.ghtheme)"))
        if not path:
            return
        try:
            saved = themes.write_file(path, dict(spec, name=t(spec["name"])))
        except (OSError, ValueError) as error:
            self.notify(t("Could not save the theme: {message}", message=error), "error", 8000)
            return
        self.notify(t("Saved {name}. Anyone with GeoHarvest or HomingPigeon can load it in "
                      "Settings.", name=saved.name), "success", 8000)

    def _load_theme(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self, t("Load a theme from a file"), "",
            t("Themes (*.ghtheme *.hptheme);;All files (*.*)"))
        if not path:
            return
        try:
            spec = themes.read_file(path)
        except OSError as error:
            self.notify(t("Could not open the file: {message}", message=error), "error", 8000)
            return
        except ValueError as error:
            self.notify(str(error), "error", 8000)
            return
        if any(mine["name"].casefold() == spec["name"].casefold()
               for mine in themes.custom_themes()) and not ConfirmDialog.ask(
                self, "Replace the theme?",
                t("You already have a theme called {name}. Replace it?", name=spec["name"]),
                "Replace"):
            return
        themes.save_custom(spec)
        key = themes.custom_key(spec["name"])
        db.set_setting("appearance", key)
        self._fill_themes()
        window = self.window_
        self._choose_theme(key)
        window.notify(t("Theme {name} added and switched on.", name=spec["name"]),
                      "success", 6000)

    def _fill_menu_list(self) -> None:
        from app.ui.main_window import NAV_ITEMS

        labels = {item[0]: item[2] for item in NAV_ITEMS}
        hidden = prefs.hidden_pages()
        blocked = self.menu_list.blockSignals(True)
        self.menu_list.clear()
        for key in prefs.ordered(list(labels), prefs.get("nav_order")):
            entry = QListWidgetItem(t(labels[key]))
            entry.setData(Qt.ItemDataRole.UserRole, key)
            flags = (entry.flags() | Qt.ItemFlag.ItemIsDragEnabled) & ~Qt.ItemFlag.ItemIsDropEnabled
            if key in prefs.ALWAYS_SHOWN:
                flags &= ~Qt.ItemFlag.ItemIsUserCheckable
            else:
                flags |= Qt.ItemFlag.ItemIsUserCheckable
                entry.setCheckState(Qt.CheckState.Unchecked if key in hidden
                                    else Qt.CheckState.Checked)
            entry.setFlags(flags)
            self.menu_list.addItem(entry)
        self.menu_list.setFixedHeight(
            self.menu_list.sizeHintForRow(0) * self.menu_list.count()
            + 2 * self.menu_list.frameWidth() + 4)
        self.menu_list.blockSignals(blocked)

    def _menu_changed(self) -> None:
        order, hidden = [], []
        for index in range(self.menu_list.count()):
            entry = self.menu_list.item(index)
            key = entry.data(Qt.ItemDataRole.UserRole)
            order.append(key)
            if key not in prefs.ALWAYS_SHOWN and entry.checkState() == Qt.CheckState.Unchecked:
                hidden.append(key)
        db.set_setting("nav_order", order)
        db.set_setting("nav_hidden", hidden)
        self.window_.apply_nav_order()

    def _reset_menu(self) -> None:
        db.set_setting("nav_order", [])
        db.set_setting("nav_hidden", [])
        self._fill_menu_list()
        self.window_.apply_nav_order()
        self.notify("The menu is back in its original order.", "success")

    @staticmethod
    def _smooth_changed(on: bool) -> None:
        db.set_setting("smooth_scroll", bool(on))
        scrolling.set_smooth(bool(on))

    def _reset_appearance(self) -> None:
        for key in prefs.APPEARANCE_KEYS:
            db.set_setting(key, prefs.DEFAULTS[key])
        scrolling.set_smooth(prefs.DEFAULTS["smooth_scroll"])
        theme.set_appearance(prefs.DEFAULTS["appearance"])
        theme.set_high_contrast(False)
        theme.set_bold_text(False)
        self.window_.change_text_size(prefs.DEFAULTS["text_size"])  # rebuilds the window
        self.window_.notify("Appearance settings reset.", "success")

    def open_licenses(self) -> None:
        """The licenses folder beside the installed app, or the notices page from source."""
        folder = Path(sys.executable).parent / "licenses"
        if getattr(sys, "frozen", False) and folder.is_dir():
            os.startfile(folder)  # noqa: S606
        else:
            open_url(f"{config.REPO_URL}/blob/main/THIRD-PARTY-NOTICES.md")

    def save_proxies(self) -> None:
        good, bad = scraper.parse_proxies(self.proxies.toPlainText())
        if bad:
            self.notify(t("These lines aren't proxies: {lines}. Fix them, then save again.",
                          lines=", ".join(bad[:3]) + (" ..." if len(bad) > 3 else "")),
                        "warn", 8000)
            return
        credentials.save_secret(scraper.PROXIES_SECRET, "\n".join(good))
        self.proxies.setPlainText("\n".join(good))
        self.notify(t("Saved {count} proxies.", count=len(good)) if len(good) > 1 else
                    t("Saved 1 proxy.") if good else "Proxies cleared: searches go direct.",
                    "success")

    def test_proxies(self) -> None:
        good, bad = scraper.parse_proxies(self.proxies.toPlainText())
        if bad or not good:
            self.proxy_status.setText(t("Nothing to test.") if not bad else
                                      t("Fix the lines that aren't proxies first."))
            return

        def check_all() -> list[str | None]:
            with ThreadPoolExecutor(8) as pool:
                return list(pool.map(scraper.check_proxy, good))

        def done(results: list[str | None]) -> None:
            working = sum(r is None for r in results)
            failed = [f"{proxy.split('@')[-1]}: {r}" for proxy, r in zip(good, results) if r]
            self.proxy_status.setText(t("{working} of {count} working.",
                                        working=working, count=len(good)) + (
                " " + t("Not working: {proxies}", proxies="; ".join(failed[:3])
                        + (" ..." if len(failed) > 3 else "")) if failed else ""))

        self.test_button.setEnabled(False)
        self.proxy_status.setText(t("Testing {count}...", count=len(good)))
        Task(check_all).start(
            on_result=self.guard(done),
            on_error=self.guard(lambda message: self.proxy_status.setText(message)),
            on_done=self.guard(lambda: self.test_button.setEnabled(True)))

    def delete_all(self) -> None:
        if self.window_.busy_page_reason():
            self.notify("Wait until the search has finished, or stop it first.", "warn")
            return
        if not ConfirmDialog.ask(self, "Delete every search and lead?",
                                 "This empties GeoHarvest's lead lists. Files you exported are "
                                 "not touched, and your settings and AI key are kept.",
                                 confirm_text="Delete everything", danger=True):
            return
        db.execute("DELETE FROM leads")
        db.execute("DELETE FROM searches")
        self.window_.refresh_status()
        self.notify("All searches and leads deleted.", "success")

    def uninstall(self) -> None:
        if self.window_.busy_page_reason():
            self.notify("Wait until the search has finished, or stop it first.", "warn")
            return
        choice = ChoiceDialog.ask(
            self, "Uninstall GeoHarvest?",
            "GeoHarvest will close and be removed from this computer, with its shortcuts.",
            [("keep", "Uninstall, keep my searches, leads and settings", "danger"),
             ("delete", "Uninstall and delete my searches, leads and settings too", "secondary"),
             (None, "Cancel", "secondary")])
        if choice is None:
            return
        try:
            updater.start_uninstall(delete_data=choice == "delete")
        except OSError as error:
            self.notify(t("The uninstaller didn't start: {error}", error=error), "error")
            return
        self.window_.quit_app()
