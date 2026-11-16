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


def test_the_update_notice_installs_only_on_update_now_and_holds_a_waiting_search(
        window, monkeypatch):
    from pathlib import Path

    from app.services import updater
    from app.ui.widgets.update_dialog import UpdatingNotice

    search_id = saved_search("waiting", resume_at=time.time() + 90)
    win = window()
    page = win.ensure_page("search")
    started, installed, quits = [], [], []
    monkeypatch.setattr(page, "run", started.append)
    monkeypatch.setattr(updater, "start_install", installed.append)
    monkeypatch.setattr(win, "quit_app", lambda: quits.append(True))
    page.pick_up()

    notice = UpdatingNotice(win, updater.Release("v9.9.9", "https://example.com"), Path("Setup"))
    notice.show()
    assert notice.now_button.text() == "Update now" and notice.later_button.text() == "Later"
    page.resume_at = time.time() - 1
    page._tick()  # the wait is over, but the question is still open
    assert not started and page.countdown.isActive()
    notice.reject()  # Later, Escape or the X
    assert not installed and not quits and not notice.isVisible()
    page._tick()
    assert started == [search_id]

    notice = UpdatingNotice(win, updater.Release("v9.9.9", "https://example.com"), Path("Setup"))
    notice.show()
    notice.now_button.click()
    assert installed == [Path("Setup")] and quits == [True]


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


def test_more_than_one_opening_hours_choice_shows_a_warning_on_the_form(window):
    page = window().ensure_page("search")
    page.niches.setText("gym")
    page.where.set("area")
    page.area_place.setText("Dubai")
    page._where_changed()
    for button in (page.open_now, page.open_24h, page.open_weekends, page.open_at):
        button.setChecked(False)
    assert page.plan.text() and "opening hours" not in page.plan.text()
    page.open_now.setChecked(True)
    assert "opening hours" not in page.plan.text()
    page.open_weekends.setChecked(True)
    assert "2 opening hours choices are on" in page.plan.text()


def test_the_google_client_spaces_out_its_requests(monkeypatch):
    client = scraper.MapsClient(proxies=[])
    client.gap = 0.1
    monkeypatch.setattr(client, "_fetch", lambda *_args: [])
    began = time.monotonic()
    for _ in range(4):
        client.fetch("q")
    client.close()
    assert time.monotonic() - began >= 3 * 0.1 * 0.7


def test_a_second_search_cannot_start_while_one_runs(window):
    win = window()
    page, history = win.ensure_page("search"), win.ensure_page("history")
    saved_search("stopped")
    history.on_show()
    history._selected = lambda: history.model.rows[0]
    before = len(searches.all_searches())
    page.worker = object()  # a search is running
    page.niches.setText("gym")
    page.start()
    history.run_again()
    history.resume()
    page.worker = None
    # the box adds ", " after a type by itself
    assert len(searches.all_searches()) == before and page.niches.text().startswith("gym")


def test_stop_then_closing_the_app_keeps_the_search_stopped():
    from app.workers.scrape import ScrapeWorker

    worker = ScrapeWorker(1)
    worker.stop("paused")
    worker.stop("running")  # the app closes before the pages in flight are done
    assert worker.ending == "paused"


def test_a_search_carrying_on_by_itself_leaves_the_form_alone(window, monkeypatch):
    search_id = saved_search("waiting", resume_at=time.time() + 90)
    page = window().ensure_page("search")
    started = []
    monkeypatch.setattr(page, "run", started.append)
    page.pick_up()
    page.niches.setText("my new search")
    page.resume_at = time.time() - 1
    page._tick()
    assert started == [search_id] and page.niches.text().startswith("my new search")
    page.resume()  # the Resume button does show the search it carries on with
    assert page.niches.text().startswith("cafe")


def test_deleting_a_search_clears_it_from_the_other_pages(window, monkeypatch):
    from app.ui.pages import history as history_module

    search_id = saved_search("stopped")
    searches.set_picked(search_id, [{"place_id": "a", "name": "a"}])
    win = window()
    page, leads, history = (win.ensure_page(name) for name in ("search", "leads", "history"))
    page.pick_up()
    page.summary.show()
    leads.select_search(search_id)
    assert leads.current_id == search_id and leads.model.rowCount() == 1
    history.on_show()
    monkeypatch.setattr(history, "_selected",
                        lambda: history.model.rows[0] if history.model.rows else None)
    monkeypatch.setattr(history_module.ConfirmDialog, "ask", lambda *_args, **_more: True)
    history.delete()
    assert leads.current_id == 0 and leads.model.rowCount() == 0
    assert page.search_id is None and not page.summary.isVisibleTo(page)
    assert not page.widen.isVisibleTo(page)


def test_a_search_ended_by_an_error_tells_the_other_pages(window):
    search_id = saved_search("running")
    win = window()
    page = win.ensure_page("search")
    heard = []
    win.search_finished.connect(heard.append)
    page.search_id, page.worker = search_id, object()
    page._on_failed("boom")
    assert heard == [search_id] and page.worker is None
    assert searches.get(search_id)["status"] == "stopped"
    assert page.resume_button.isVisibleTo(page)
    assert "error" in page.status.text()


def test_a_big_leads_list_is_not_reworked_row_by_row(window, monkeypatch):
    from app.ui.widgets.leads_model import LeadsModel, LeadsProxy

    model = LeadsModel()
    proxy = LeadsProxy(model)
    model.set_leads([{"place_id": f"p{n}", "name": f"Cafe {n}"} for n in range(500)])
    assert model.haystacks == [None] * 500  # the filter text is only made when searched
    signals = []
    model.dataChanged.connect(lambda *_args: signals.append(1))
    model.update_many([f"p{n}" for n in range(500)], {"exported": "2026-11-16"})
    assert len(signals) == 1 and model.leads[499]["exported"] == "2026-11-16"
    proxy.set_filter("cafe p499")
    assert [lead["place_id"] for lead in proxy.visible_leads()] == ["p499"]
    model.update("p499", {"name": "Gym"})  # a changed row is searched by its new text
    assert proxy.visible_leads() == []

    # picking a search reads its leads once, and filling the form works the plan out once
    search_id = saved_search("stopped")
    win = window()
    leads, page = win.ensure_page("leads"), win.ensure_page("search")
    reads, plans = [], []
    real_leads, real_queries = searches.leads, searches.build_queries
    monkeypatch.setattr(searches, "leads", lambda sid: reads.append(sid) or real_leads(sid))
    monkeypatch.setattr(searches, "build_queries",
                        lambda options: plans.append(1) or real_queries(options))
    leads.select_search(search_id)
    assert reads == [search_id]
    page.load_options(searches.get(search_id)["options"])
    assert len(plans) == 1 and "1 searches" in page.plan.text()


def test_free_up_space_in_settings_asks_first_then_trims(window, monkeypatch):
    import json

    from app.core import tidy
    from app.ui.pages import settings

    class NowTask:  # the real one runs on another thread
        def __init__(self, work, *args):
            self.work, self.args = work, args

        def start(self, on_result=None, on_error=None):
            on_result(self.work(*self.args))

    search_id = saved_search("done")
    db.execute("INSERT INTO candidates(search_id, place_id, data, dropped) VALUES(?, ?, ?, ?)",
               (search_id, "a", json.dumps({"place_id": "a", "about": "x" * 2_000_000}),
                "no website"))
    page = window().ensure_page("settings")
    asked = []
    monkeypatch.setattr(settings, "Task", NowTask)
    monkeypatch.setattr(settings.ConfirmDialog, "ask",
                        lambda _parent, title, *_rest, **_more: asked.append(title))  # Cancel
    page.free_space()
    assert asked == ["Free up about 2 MB?"] and tidy.spare_bytes() > 2_000_000
    monkeypatch.setattr(settings.ConfirmDialog, "ask", lambda *_args, **_more: True)
    page.free_space()
    assert tidy.spare_bytes() == 0
    monkeypatch.setattr(settings.ConfirmDialog, "ask",
                        lambda *_args, **_more: asked.append("again"))
    page.free_space()  # nothing left: a message, no question
    assert asked == ["Free up about 2 MB?"]


def test_a_held_search_that_visits_websites_shows_resume_when_the_app_opens(window):
    # 0.3.3 raised "no attribute 'step'" here: the tiles were filled before any search ran
    search_id = searches.create({"niches": ["cafe"], "countries": ["Pakistan"],
                                 "cities": ["Lahore, Pakistan"], "find_emails": True})
    searches.set_status(search_id, "paused")
    found = [{"place_id": p, "status": "Open", "phone": "+92 1", "name": p,
              "website": "https://example.com"} for p in "abc"]
    searches.save_candidates(search_id, found, searches.get(search_id)["options"])
    searches.recover_interrupted()
    page = window().page("search")
    page.pick_up()
    assert page.tile_found.value_label.text() == "3"
    assert page.resume_button.isVisibleTo(page)


def test_a_paused_search_shows_its_numbers_and_new_leads_join_the_list(window):
    search_id = saved_search("paused")
    found = [{"place_id": p, "status": "Open", "phone": "+92 1", "name": p} for p in "abc"]
    searches.save_candidates(search_id, found, searches.get(search_id)["options"])
    searches.set_picked(search_id, found[:2])
    searches.recover_interrupted()
    win = window()
    page = win.page("search")
    page.pick_up()
    assert page.tile_found.value_label.text() == "3" and page.tile_phone.value_label.text() == "3"
    assert page.tile_best.value_label.text().startswith("2 ")

    win.show_page("leads")
    leads = win.page("leads")
    assert leads.current_id == search_id and leads.model.rowCount() == 2
    first = leads.model.leads[0]
    searches.set_picked(search_id, found)  # the next batch of a running search
    leads.show_new_leads(search_id)
    assert leads.model.rowCount() == 3 and leads.model.leads[0] is first  # added, not reloaded
    leads.show_new_leads(search_id + 1)  # another search's batch changes nothing on show
    assert leads.model.rowCount() == 3
