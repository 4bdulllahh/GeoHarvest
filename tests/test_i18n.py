"""Tests for the app's languages: complete translations, templates, right to left."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app import i18n  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import i18n as i18n_tool  # noqa: E402  (tools/i18n.py)


@pytest.fixture(autouse=True)
def english_afterwards():
    yield
    i18n.set_language("en")


# --- the catalogs -----------------------------------------------------------
@pytest.mark.parametrize("code", ["ar", "de", "es", "fr"])
def test_every_language_has_every_string_with_the_same_fields(code):
    """New English text needs a translation in every language. See tools/i18n.py."""
    problems = i18n_tool.problems(code)
    assert not problems, (
        f"{len(problems)} translation problem(s) in {code}.json, for example "
        f"{problems[:5]}. Run: python tools/i18n.py missing {code}")


# --- t() ----------------------------------------------------------------------
def test_english_text_is_returned_unchanged_in_english():
    assert i18n.t("Save") == "Save"
    assert i18n.t("{total:,} leads", total=1200) == "1,200 leads"


def test_text_is_translated_and_templates_filled_in():
    i18n.set_language("de")
    assert i18n.t("Save") == "Speichern"
    assert i18n.t("{total:,} leads", total=1200) == "1,200 Leads"


def test_unknown_text_and_non_text_pass_straight_through():
    i18n.set_language("es")
    assert i18n.t("acme@example.com") == "acme@example.com"
    assert i18n.t(42) == 42
    assert i18n.t("") == ""


def test_a_broken_translation_falls_back_to_english(monkeypatch):
    i18n.set_language("de")
    monkeypatch.setitem(i18n.catalog("de"), "{total:,} leads", "{gesamt:,} Leads")
    assert i18n.t("{total:,} leads", total=2) == "2 leads"


def test_the_computers_language_is_used_when_nothing_is_chosen():
    assert i18n.system_language("de_DE") == "de"
    assert i18n.system_language("ar-AE") == "ar"
    assert i18n.system_language("ja_JP") == "en"
    assert i18n.system_language(None) == "en"
    assert i18n.is_rtl("ar") and not i18n.is_rtl("fr")


# --- the window ---------------------------------------------------------------
pytest.importorskip("PyQt6", reason="PyQt6 is not installed")


@pytest.fixture
def qt_app():
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
    from PyQt6.QtCore import Qt

    app.setLayoutDirection(Qt.LayoutDirection.LeftToRight)


@pytest.fixture
def store(tmp_path, monkeypatch):
    from app import config
    from app.core import db

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    db.close()
    db.init(tmp_path / "test.db")
    yield
    db.close()


def test_rows_of_buttons_start_at_the_right_edge_in_arabic(qt_app):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QPushButton, QWidget

    from app.ui.widgets.flow import FlowLayout

    holder = QWidget()
    holder.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    layout = FlowLayout(holder, margin=0, spacing=8)
    first, second = QPushButton("one"), QPushButton("two")
    layout.addWidget(first)
    layout.addWidget(second)
    holder.resize(400, 60)
    holder.show()
    qt_app.processEvents()
    assert first.geometry().right() > second.geometry().right()
    assert first.geometry().right() >= 390
    holder.close()


@pytest.mark.parametrize("code", ["ar", "de", "es", "fr"])
def test_every_page_opens_in_every_language(qt_app, store, code):
    from PyQt6.QtCore import Qt

    from app.ui.main_window import NAV_ITEMS, MainWindow

    window = MainWindow()
    try:
        window.change_language(code)
        assert i18n.language() == code
        expected = Qt.LayoutDirection.RightToLeft if code == "ar" \
            else Qt.LayoutDirection.LeftToRight
        assert qt_app.layoutDirection() == expected
        for key, *_rest in NAV_ITEMS + [("settings",)]:
            window.show_page(key)
            assert window.page(key) is not None, key
        # The sidebar is in the chosen language
        assert window._nav["settings"].title_label.text() == i18n.t("Settings")
        assert window._nav["settings"].title_label.text() != "Settings"
    finally:
        window.change_language("en")
        window.close()
        window.deleteLater()


def test_the_language_choice_is_remembered(qt_app, store):
    from app.core import db, prefs
    from app.ui.main_window import MainWindow

    window = MainWindow()
    try:
        window.change_language("fr")
        assert db.get_setting("language") == "fr"
        assert prefs.language("de_DE") == "fr"
    finally:
        window.change_language("en")
        window.close()
        window.deleteLater()
