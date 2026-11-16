"""The search job: batches of three steps, until the maximum is reached or nothing is left.

1. Search Google until about ``BATCH`` new businesses fit the requirements Google's
   listing shows. The searches take turns a page at a time, so the batches spread over
   every city and business type. Every business listed is stored as a candidate, with
   the reason it was left out if a requirement rules it out.
2. Check those websites (emails, social media, company age, owner), best first, and
   leave out the ones a website requirement rules out (no email found...).
3. Smart mode's AI checks the leads left, if it is on.

The ones that fit become leads straight away (best first, at most the maximum), then the
next batch starts. Small batches keep an older PC responsive: nothing waits on thousands
of websites at once. Once Google has nothing left, the search goes deeper if it is under
the minimum, and then on to the maximum: each search Google gave a full list for is run
again as four smaller map views, and those are split again where they are full too
(``search.deep_queries``).

Everything is saved the moment it arrives, with the page each query has reached, so
pressing Pause or Stop, closing the app or Google pushing back loses nothing: resuming
carries on from there. When Google pushes back the websites and AI still finish (they don't
touch Google), then the search waits and the Search page starts it again when the time is up.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, wait

import httpx
from PyQt6.QtCore import pyqtSignal

from app.core import ai, db, enrich, scraper
from app.core import search as searches
from app.workers.base import Signals, Worker

DEFAULT_PARALLEL = 4
BATCH = 100  # businesses found before their websites are checked
# ...or this many Google pages, whichever comes first. With strict requirements 1 business
# in 80 fits (the user's search, 2026-11), so 100 took about 400 pages with no new leads
# on screen; 50 pages is under a minute at Normal speed
BATCH_PAGES = 50
# A query whose last pages held only businesses other queries already found is ended: the
# rest is nearly always more of the same ("builder" after "contractor" in the same city).
# A judgement, not measured live: raise it if searches of similar types come up short
STALE_PAGES = 2
# Google's limit: first wait this many seconds inside the run and carry on at the slowest
# pace. Only a limit straight after the last of these ends Google for the run, and the
# search then waits the long way (search.GOOGLE_WAITS). Judgements, not measured
SHORT_WAITS = (120, 300)
# No connection: try again every OFFLINE_WAIT seconds, OFFLINE_TRIES times in a row (10
# minutes), before the queries are given up as failing and the search stops
OFFLINE_WAIT = 30
OFFLINE_TRIES = 20
SAVE_EVERY = 10  # pages between saves of how far each query has got (and at every batch's end)
# Website visits at once, by the Speed setting (parallel Google searches). Visits are slow
# to answer, but reading the pages takes the PC's time, so Gentle suits older PCs
VISITS_BY_SPEED = {2: 6, 4: 12, 8: 16}


class ScrapeSignals(Signals):
    step = pyqtSignal(int)               # step 1, 2 or 3 has started
    found = pyqtSignal(int, int)         # businesses that fit so far, how many have a phone
    checked = pyqtSignal(int, int, int)  # websites checked, websites to check, emails found
    scored = pyqtSignal(int, int)        # leads the AI has checked, leads to check
    leads = pyqtSignal(int)              # leads that meet every requirement so far
    limited = pyqtSignal(int)            # Google's limit: carrying on in this many seconds
    offline = pyqtSignal()               # no connection: trying again until it is back


class ScrapeWorker(Worker):
    def __init__(self, search_id: int):
        super().__init__()
        self.signals = ScrapeSignals()
        self.search_id = search_id
        self._stop = threading.Event()
        self.ending = "stopped"       # the search's status after stop()
        self.blocked = False          # Google limited us: no more Google in this run
        self.blocked_at = 0.0
        self.short_waits = 0          # short waits used up since the last good stretch
        self.wait_until = 0.0         # a short wait is on until then
        self.limit_at_page = 0        # self.fetched when Google last limited us
        self.offline_waits = 0        # waits for the connection since the last good page
        self._limit_lock = threading.Lock()
        self.fetched = 0              # Google pages in this run
        self.tried: set[str] = set()  # websites visited in this run, whatever happened
        self.pages: dict = {}         # searches under way: query -> its pages still to come
        self.following: dict = {}     # where each query goes next, once its page is saved
        self.failed: set[str] = set()  # searches that failed once in this run
        self.stale: dict[str, int] = {}  # query -> pages in a row with nothing new
        self.listed: dict[str, int] = {}  # query -> businesses Google has listed for it
        self.cut: set[str] = set()    # searches Stop or a limit ended before their last page
        self.ai_checked = 0           # leads Smart mode checked in this run

    def stop(self, ending: str = "stopped") -> None:
        """Finish the pages in flight, keep what is ready, then end normally (unlike
        cancel(), which goes silent). ``ending``: stopped, paused, or running when the app
        is closing, so it carries on by itself next time."""
        self.ending = ending
        self._stop.set()

    def back_off(self) -> bool:
        """Google limited a request. Wait a short while and say so; False once the short
        waits are used up (or Stop was pressed), which ends Google for this run. Every
        thread that meets the limit waits out the same pause."""
        with self._limit_lock:
            now = time.time()
            if self.blocked:
                return False
            first = now >= self.wait_until
            if first:
                if self.fetched - self.limit_at_page >= searches.CLEAR_AFTER_PAGES:
                    self.short_waits = 0  # it went well for a while: start over
                if self.short_waits >= len(SHORT_WAITS):
                    self.blocked_at = now
                    self.blocked = True
                    return False
                seconds = SHORT_WAITS[self.short_waits]
                self.short_waits += 1
                self.limit_at_page = self.fetched
                self.wait_until = now + seconds
                self.client.slow = scraper.MAX_SLOW  # eases off by itself (M8)
                self.log(f"Google asked to slow down: waiting {seconds} seconds", "warn")
                self.signals.limited.emit(seconds)
        self._stop.wait(max(0.0, self.wait_until - time.time()))
        if first and not self._stop.is_set():
            self.signals.step.emit(1)  # the status line says "Searching Google" again
        return not self._stop.is_set()

    def wait_for_internet(self) -> bool:
        """A request didn't get through. Wait a little with every search thread and say so;
        False once that has gone on too long, and the query is given up as before."""
        with self._limit_lock:
            now = time.time()
            if now >= self.wait_until:
                if self.offline_waits >= OFFLINE_TRIES:
                    return False
                self.offline_waits += 1
                self.wait_until = now + OFFLINE_WAIT
                if self.offline_waits == 1:
                    self.log("No connection: trying again until it is back", "warn")
                    self.signals.offline.emit()
        self._stop.wait(max(0.0, self.wait_until - time.time()))
        return True

    def work(self) -> dict:
        record = searches.get(self.search_id)
        options = record["options"]
        low, high = searches.leads_wanted(options)
        visiting = searches.visits_websites(options)
        searches.adopt_leads(self.search_id)
        searches.set_status(self.search_id, "running")
        ai_error, have, searched = None, 0, False
        self.client = scraper.MapsClient()
        self.client.gap = searches.google_gap(
            int(db.get_setting("parallel_searches", DEFAULT_PARALLEL)),
            record["progress"].get("waits", 0))
        try:
            while True:
                fetched_before = self.fetched
                done_before = len(searches.get(self.search_id)["progress"].get("done", []))
                searched = self.search_google(options, BATCH, BATCH_PAGES)
                if visiting and not self._stop.is_set():
                    self.check_websites(options)
                if options["smart"] and not self._stop.is_set() and not ai_error:
                    ai_error = self.score_with_ai(options)
                have = self.keep(options, visiting, high)
                if self._stop.is_set() or self.blocked or ai_error or have >= high:
                    break
                if searched:
                    # Google has nothing more for these searches. Digging deeper starts
                    # only under the minimum; once started it goes on to the maximum (the
                    # user's choice, 2026-11), splitting only the views that came back full
                    digging = searches.get(self.search_id)["progress"].get("deep")
                    if not (have < low or digging) or not searches.deep_queries(
                            self.search_id, options):
                        break
                elif self.fetched == fetched_before and len(
                        searches.get(self.search_id)["progress"].get("done", [])) == done_before:
                    # Not one page: the queries left keep failing; resuming tries them again.
                    # (Counting pages, not businesses: a batch whose new ones all fail the
                    # website check is still progress)
                    break
        finally:
            self.client.close()
        stopped = self._stop.is_set()
        if (searched or have >= high) and not stopped and not ai_error:
            status = "done"
        elif stopped and not (self.blocked and self.ending == "running"):
            status = self.ending
        elif stopped:
            status = "waiting"  # closed while limited: opening the app waits the time out
        elif self.blocked and not ai_error:
            status = "waiting"
        else:
            status = "stopped"
        if status == "waiting":
            searches.wait_for_google(self.search_id, self.blocked_at, self.fetched)
        else:
            searches.set_status(self.search_id, status)
        dropped = searches.dropped_counts(self.search_id)
        return {"status": status, "found": have, "wanted": low, "most": high,
                "blocked": self.blocked, "ai_error": ai_error, "dropped": dropped,
                "listed": searches.tally(self.search_id)["fits"] + sum(dropped.values())}

    # --- step 1 -----------------------------------------------------------------
    def search_google(self, options: dict, batch: int, most_pages: int) -> bool:
        """Fetch pages until ``batch`` more candidates fit or ``most_pages`` pages are in, the
        searches taking turns a page at a time (each one's first page, then each one's
        second...). Searches a full batch cut off carry on in the next batch. True once
        every query is done."""
        record = searches.get(self.search_id)
        all_queries = searches.all_queries(self.search_id, options)
        done = set(record["progress"].get("done", []))
        left = [q for q in all_queries if q not in done]
        at = record["progress"].get("at", {})
        # Those not started go first: every search's first page before anyone's second
        waiting = deque([q for q in left if q not in self.pages and q not in at] +
                        [q for q in left if q in self.pages or q in at])
        lock = threading.Lock()
        had = searches.tally(self.search_id)
        goal = had["fits"] + batch
        last_page = self.fetched + most_pages
        state = {"finished": len(all_queries) - len(left), "total": len(all_queries),
                 "fits": had["fits"], "phones": had["phones"], "busy": 0}
        unsaved: dict = {"done": [], "at": {}, "full": [], "pages": 0}
        self.signals.step.emit(1)
        self.signals.found.emit(state["fits"], state["phones"])
        self.report(state["finished"], state["total"])

        def no_more_google() -> bool:
            return self._stop.is_set() or self.blocked

        def save() -> None:
            """Write the pages reached since the last save (call with the lock held)."""
            searches.save_pages(self.search_id, unsaved["done"], unsaved["at"],
                                unsaved["full"])
            unsaved.update(done=[], at={}, full=[], pages=0)

        def cut_short(query: str) -> bool:
            """Asked by the query's search before each further page: noted, because a
            search that ends here is not finished, while one that ends on Google's empty
            last page is, even if Stop or a limit arrived in the same moment."""
            if no_more_google():
                self.cut.add(query)
            return query in self.cut

        def next_page(query: str) -> list[dict] | None:
            """The query's next page, None once it has no more. Raises on errors."""
            pages = self.pages.get(query)
            if pages is None:
                pages = self.pages[query] = iter(scraper.search(
                    self.client, query, cancelled=lambda: cut_short(query),
                    start=at.get(query),
                    remember=lambda offset, view: self.following.__setitem__(
                        query, [offset, view])))
            return next(pages, None)

        def take_turn(query: str) -> bool:
            """One page of one query; False when Google is over for this run."""
            try:
                page = next_page(query)
            except scraper.Blocked:
                self.pages.pop(query, None)  # its search starts again from the page saved
                with lock:
                    waiting.appendleft(query)
                return self.back_off()
            except (httpx.HTTPError, ValueError) as error:
                self.pages.pop(query, None)
                if isinstance(error, httpx.TransportError) and self.wait_for_internet():
                    with lock:
                        waiting.appendleft(query)  # again, from the page it had reached
                    return not self._stop.is_set()
                # One retry for a dropped connection; after that the query stays
                # un-done, so resuming the search tries it again
                if query in self.failed:
                    self.log(f"Skipped '{query}' for now: {error}", "warn")
                    return True
                self.failed.add(query)
                self._stop.wait(3)  # Stop and Pause don't sit this out
                with lock:
                    waiting.append(query)
                return True
            with lock:
                if page is None and query in self.cut:
                    return False  # not finished: resuming carries on with it
                if page is not None:
                    self.fetched += 1
                    if self.offline_waits:  # the connection is back
                        self.offline_waits = 0
                        self.signals.step.emit(1)
                    new, fresh = searches.add_candidates(self.search_id, page, options)
                    self.stale[query] = 0 if fresh else self.stale.get(query, 0) + 1
                    # A resumed query starts from the page it had reached
                    self.listed[query] = self.listed.get(
                        query, (at.get(query) or [0])[0]) + len(page)
                    state["fits"] += len(new)
                    state["phones"] += sum(bool(lead.get("phone")) for lead in new)
                    self.signals.found.emit(state["fits"], state["phones"])
                    unsaved["pages"] += 1
                if page is None or self.stale[query] >= STALE_PAGES:
                    self.pages.pop(query, None)
                    self.following.pop(query, None)
                    done.add(query)
                    unsaved["done"].append(query)
                    # Ended by Google with a full list (not by us, for repeating): worth
                    # splitting if the search has to dig deeper
                    if page is None and self.listed.get(query, 0) >= searches.DEEP_AT:
                        unsaved["full"].append(query)
                    unsaved["at"].pop(query, None)
                    state["finished"] += 1
                    self.report(min(state["finished"], state["total"]), state["total"], query)
                else:
                    if query in self.following:
                        at[query] = unsaved["at"][query] = self.following.pop(query)
                    waiting.append(query)  # its next page after everyone else's
                if unsaved["pages"] >= SAVE_EVERY:
                    save()
            return True

        def run() -> None:
            while not no_more_google():
                with lock:
                    if state["fits"] >= goal or self.fetched >= last_page:
                        return
                    # Nothing waiting but pages in flight: their queries come back for
                    # their next page, so stay. Leaving here left the last few queries
                    # to one thread
                    query = waiting.popleft() if waiting else None
                    if query is None and not state["busy"]:
                        return
                    state["busy"] += query is not None
                if query is None:
                    time.sleep(0.05)
                    continue
                try:
                    if not take_turn(query):
                        return
                finally:
                    with lock:
                        state["busy"] -= 1

        parallel = max(1, int(db.get_setting("parallel_searches", DEFAULT_PARALLEL)))
        try:
            with ThreadPoolExecutor(parallel) as pool:
                for future in [pool.submit(run) for _ in range(parallel)]:
                    future.result()
        finally:
            save()  # whatever happened, the pages that came in are not asked for again
        return set(all_queries) <= done

    # --- step 2 -----------------------------------------------------------------
    def check_websites(self, options: dict) -> None:
        """Visit the website of every candidate not checked yet, best first, and leave out
        the ones a website requirement (age, email, social media...) rules out."""
        enricher = enrich.Enricher(wayback=searches.age_filtered(options))
        site_text = options["smart"] and bool(db.get_setting("ai_read_site", False))
        lock = threading.Lock()
        fits = searches.candidates(self.search_id)
        checked = [lead for lead in fits if lead.get("enriched")]
        todo = sorted((lead for lead in fits
                       if not lead.get("enriched") and lead["place_id"] not in self.tried),
                      key=searches.score, reverse=True)
        self.tried.update(lead["place_id"] for lead in todo)
        state = {"checked": len(checked), "total": len(checked) + len(todo),
                 "emails": sum(bool(lead.get("emails")) for lead in checked)}
        self.signals.step.emit(2)
        self.signals.checked.emit(state["checked"], state["total"], state["emails"])

        def check(lead: dict) -> None:
            if self._stop.is_set():
                return
            try:
                fields = enricher.enrich(lead, options["find_emails"],
                                         find_owner=options["find_owner"],
                                         site_text=site_text)
            except Exception as error:  # noqa: BLE001 - one odd website must not end the search
                if self._stop.is_set():
                    return  # Stop cut the connection; resuming checks this site again
                self.log(f"Could not check {lead.get('website')}: {error}", "warn")
                fields = {"enriched": True}
            fields.setdefault("enriched", True)
            dropped = searches.why_not_checked({**lead, **fields}, options)
            with lock:
                if self._stop.is_set():
                    return  # possibly half-checked when Stop cut the connection
                searches.check_candidate(self.search_id, lead["place_id"], fields, dropped)
                state["checked"] += 1
                state["emails"] += bool(fields.get("emails")) and dropped is None
                self.signals.checked.emit(state["checked"], state["total"], state["emails"])

        speed = int(db.get_setting("parallel_searches", DEFAULT_PARALLEL))
        pool = ThreadPoolExecutor(VISITS_BY_SPEED.get(speed, 12))
        try:
            futures = [pool.submit(check, lead) for lead in todo]
            while not self._stop.is_set() and wait(futures, timeout=0.5).not_done:
                pass
        finally:
            # Stop drops the visits still waiting or under way (closing the connections
            # cuts those short); resuming picks them up
            pool.shutdown(wait=not self._stop.is_set(), cancel_futures=True)
            enricher.close()

    # --- step 3 -----------------------------------------------------------------
    def score_with_ai(self, options: dict) -> str | None:
        """Smart mode: the AI checks every lead left that it hasn't seen. Returns the error
        that switched it off, if one did."""
        cfg = ai.settings()
        if cfg is None:
            return None
        self.signals.step.emit(3)
        visiting = searches.visits_websites(options)
        todo = sorted((lead for lead in searches.candidates(self.search_id)
                       if "ai_score" not in lead and (lead.get("enriched") or not visiting)
                       and ai.worth_checking(cfg, lead)),
                      key=searches.score, reverse=True)
        if cfg["max_leads"]:  # the user's limit on the key's allowance, for the whole run
            todo = todo[:max(0, cfg["max_leads"] - self.ai_checked)]
        pace = ai.Pace(cfg["per_minute"])
        low = f"AI score under {cfg['min_score']}"
        for start in range(0, len(todo), ai.BATCH_SIZE):
            if self._stop.is_set():
                break
            batch = todo[start: start + ai.BATCH_SIZE]
            try:
                pace.wait(self._stop.is_set)
                scored = ai.score(cfg, ", ".join(options["niches"]), batch)
            except ai.AIError as error:
                if error.fatal:
                    return str(error)
                self.log(str(error), "warn")
                continue
            except Exception as error:  # noqa: BLE001 - an AI hiccup must not end the search
                self.log(f"Smart mode skipped a batch: {error}", "warn")
                continue
            self.ai_checked += len(batch)
            for lead in batch:
                fields = scored.get(lead["place_id"])
                if fields is None:
                    continue  # left unscored; resuming the search tries again
                too_low = bool(cfg["min_score"]) and fields["ai_score"] < cfg["min_score"]
                searches.check_candidate(self.search_id, lead["place_id"], fields,
                                         low if too_low else None)
            self.signals.scored.emit(min(start + len(batch), len(todo)), len(todo))
        return None

    def keep(self, options: dict, visiting: bool, most: int) -> int:
        """Make the best ``most`` candidates that meet the requirements the leads: fully
        checked ones before any Stop left unchecked, AI-checked before unchecked, known
        company ages before unknown ones, then the quality score."""
        self.signals.step.emit(3)
        fits = searches.candidates(self.search_id)
        # Until its website is checked, nobody knows if a website requirement is met
        must_check = searches.age_filtered(options) or any(
            options[key] for key in searches.FROM_WEBSITE_REQUIREMENTS)
        if visiting and must_check:
            fits = [lead for lead in fits if lead.get("enriched")]

        def key(lead: dict) -> tuple:
            return (bool(lead.get("enriched") or not visiting),
                    "ai_score" in lead or not options["smart"],
                    lead.get("ai_score", 0),
                    "age_years" in lead or not searches.age_filtered(options),
                    searches.score(lead))

        kept = sorted(fits, key=key, reverse=True)[:most]
        searches.set_picked(self.search_id, kept)
        self.signals.leads.emit(len(kept))
        return len(kept)
