"""The wheel, the country and city lists, the model list and the search buttons, headless."""
from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PyQt6.QtGui import QWheelEvent  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QListWidget, QScrollArea, QSpinBox, QVBoxLayout, QWidget  # noqa: E402

from app.core import db, scraper  # noqa: E402
from app.core import search as searches  # noqa: E402
from app.ui import scrolling  # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    scrolling.install(app, True)
    yield app


@pytest.fixture
def store(tmp_path):
    db.close()
    db.init(tmp_path / "test.db")
    yield
    db.close()


def wheel(widget, delta=-120, pixels=0):
    pos = widget.rect().center()
    event = QWheelEvent(QPointF(pos), QPointF(widget.mapToGlobal(pos)), QPoint(0, pixels),
                        QPoint(0, delta), Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                        Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(widget, event)
    QTest.qWait(260)


@pytest.fixture
def page_with_list(qt_app):
    """A scrolling page with a list and a number box in it."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.resize(300, 300)
    content = QWidget()
    layout = QVBoxLayout(content)
    items = QListWidget()
    items.addItems([str(n) for n in range(50)])
    items.setFixedHeight(200)
    box = QSpinBox()
    box.setRange(0, 100)
    box.setValue(50)
    box.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    filler = QWidget()
    filler.setFixedHeight(2000)
    layout.addWidget(items)
    layout.addWidget(box)
    layout.addWidget(filler)
    area.setWidget(content)
    area.show()
    qt_app.processEvents()
    yield area, items, box
    scrolling.set_smooth(True)
    area.close()


@pytest.mark.parametrize("smooth", [True, False])
def test_a_list_at_its_end_keeps_the_page_still(page_with_list, smooth):
    area, items, _box = page_with_list
    scrolling.set_smooth(smooth)
    items.verticalScrollBar().setValue(items.verticalScrollBar().maximum())
    wheel(items.viewport())
    wheel(items.viewport(), pixels=-40)  # a touchpad
    assert area.verticalScrollBar().value() == 0
    items.verticalScrollBar().setValue(0)
    wheel(items.viewport())
    assert items.verticalScrollBar().value() > 0 and area.verticalScrollBar().value() == 0


def test_a_list_with_nothing_to_scroll_lets_the_page_move(page_with_list):
    area, items, _box = page_with_list
    items.clear()
    QTest.qWait(50)  # the list lays itself out
    wheel(items.viewport())
    assert area.verticalScrollBar().value() > 0


def test_the_wheel_only_changes_a_number_box_that_is_being_used(page_with_list):
    _area, _items, box = page_with_list
    wheel(box)  # Qt then offers a real wheel to the page behind (not one sent by a test)
    assert box.value() == 50
    box.setFocus()
    if box.hasFocus():  # needs the window active, which a headless run may not give
        wheel(box)
        assert box.value() != 50


def test_clicking_a_row_ticks_it_once(qt_app):
    from app.ui.widgets.checklist import CheckList

    box = CheckList("Search")
    box.set_items([("a", "Albania"), ("b", "Belgium")], set())
    box.resize(400, 300)
    box.show()
    qt_app.processEvents()
    rect = box.list.visualItemRect(box.list.item(0))
    words, switch = rect.left() + 150, rect.left() + 8
    for x, expected in ((words, ["a"]), (words, []), (switch, ["a"]), (switch, []),
                        (words, ["a"]), (switch, []), (switch, ["a"]), (words, [])):
        QTest.mouseClick(box.list.viewport(), Qt.MouseButton.LeftButton,
                         pos=QPoint(x, rect.center().y()))
        assert box.checked() == expected
        QTest.qWait(QApplication.doubleClickInterval() + 50)
    box.close()


@pytest.fixture
def window(qt_app, store):
    from app.ui.main_window import MainWindow

    made = []

    def build():
        made.append(MainWindow())
        return made[-1]

    yield build
    for item in made:
        page = item.page("search")
        if page is not None:
            page.countdown.stop()
        item.deleteLater()


def wait_until(check, seconds=8):
    end = time.monotonic() + seconds
    while not check() and time.monotonic() < end:
        QTest.qWait(30)
    assert check()


def test_the_model_arrow_loads_the_list_or_asks_for_a_key(window, monkeypatch):
    from app.core import ai

    win = window()
    win.show_page("smart")
    page = win.page("smart")
    page.provider.set("gemini")
    page._provider_changed("gemini")
    assert page.model.count() == 0
    page.key.clear()
    calls = []
    monkeypatch.setattr(ai, "list_models", lambda cfg: calls.append(cfg) or ["one", "two"])
    page.model.showPopup()  # no key yet: nothing to ask with
    assert not calls
    page.key.setText("a key")
    opened = []
    monkeypatch.setattr(type(page.model), "showPopup", lambda self: opened.append(self.count()))
    page._models_wanted()
    wait_until(lambda: page.model.count() == 2 and page.load_button.isEnabled())
    assert opened == [2] and calls[0]["key"] == "a key"
    assert page.model.lineEdit().text() == "one"  # gemini's default isn't on the list

    # In the background it never changes what is saved
    page.model.clear()
    page.model.lineEdit().setText("my-own-model")
    page._load_quietly()
    wait_until(lambda: page.model.count() == 2 and page.load_button.isEnabled())
    assert page.model.lineEdit().text() == "my-own-model"


def saved_search(status: str, **progress) -> int:
    search_id = searches.create({"niches": ["cafe"], "countries": ["Pakistan"],
                                 "cities": ["Lahore, Pakistan"], "find_emails": False})
    searches.set_status(search_id, status)
    for key, value in progress.items():
        record = searches.get(search_id)["progress"]
        record[key] = value
        searches._save_progress(search_id, record)
    return search_id


def test_opening_the_app_shows_a_paused_search_without_starting_it(window):
    search_id = saved_search("paused")
    searches.recover_interrupted()
    win = window()
    assert win.current == "search"
    page = win.page("search")
    page.pick_up()
    assert page.worker is None and page.search_id == search_id
    assert page.resume_button.isVisibleTo(page) and page.stop_button.isVisibleTo(page)
    page.stop_search()
    assert searches.get(search_id)["status"] == "stopped"
    assert page.resume_button.isVisibleTo(page) and not page.stop_button.isVisibleTo(page)


def test_a_search_waiting_for_google_counts_down_then_starts_by_itself(window, monkeypatch):
    search_id = saved_search("waiting", resume_at=time.time() + 90)
    page = window().ensure_page("search")
    started = []
    monkeypatch.setattr(page, "run", started.append)
    page.pick_up()
    assert page.countdown.isActive() and "1:30" in page.status.text()
    assert not page.start_button.isVisibleTo(page)
    assert page.resume_button.text() == "Resume now"
    page.resume_at = time.time() - 1  # the wait is over, even if the app was closed for it
    page._tick()
    assert started == [search_id] and not page.countdown.isActive()


def test_a_search_cut_off_by_closing_the_app_carries_on_when_it_opens(window, monkeypatch):
    older, newest = saved_search("running"), saved_search("running")
    searches.recover_interrupted()
    assert searches.get(older)["status"] == "stopped"
    assert searches.get(newest)["status"] == "interrupted"
    page = window().ensure_page("search")
    started = []
    monkeypatch.setattr(page, "run", started.append)
    page.pick_up()
    assert started == [newest]


def test_an_old_finished_or_stopped_search_never_starts_by_itself(window, monkeypatch):
    stopped = saved_search("stopped")
    page = window().ensure_page("search")
    started = []
    monkeypatch.setattr(page, "run", started.append)
    page.pick_up()
    assert not started and page.resume_button.isVisibleTo(page) and page.search_id == stopped
    assert page.start_button.isVisibleTo(page)
    saved_search("done")
    page.pick_up()  # the newest search finished: nothing to offer
    assert not started and page.search_id is None
    assert not page.resume_button.isVisibleTo(page)


def test_the_google_client_spaces_out_its_requests(monkeypatch):
    client = scraper.MapsClient(proxies=[])
    client.gap = 0.1
    monkeypatch.setattr(client, "_fetch", lambda *_args: [])
    began = time.monotonic()
    for _ in range(4):
        client.fetch("q")
    client.close()
    assert time.monotonic() - began >= 3 * 0.1 * 0.7
