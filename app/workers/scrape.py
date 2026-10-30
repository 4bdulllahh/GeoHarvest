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
of websites at once. Once Google has nothing left, the search goes deeper only while it is
under the minimum: each city search Google cut short is run again in small map views
(``search.deep_queries``).

Everything is saved the moment it arrives and a query is only marked done once all
its pages are in, so pressing Stop, closing the app or Google pushing back loses
nothing: resuming carries on, and Stop still keeps what is ready.
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
# Website visits at once, by the Speed setting (parallel Google searches). Visits are slow
# to answer, but reading the pages takes the PC's time, so Gentle suits older PCs
VISITS_BY_SPEED = {2: 6, 4: 12, 8: 16}


class ScrapeSignals(Signals):
    step = pyqtSignal(int)               # step 1, 2 or 3 has started
    found = pyqtSignal(int, int)         # businesses that fit so far, how many have a phone
    checked = pyqtSignal(int, int, int)  # websites checked, websites to check, emails found
    scored = pyqtSignal(int, int)        # leads the AI has checked, leads to check
    leads = pyqtSignal(int)              # leads that meet every requirement so far


class ScrapeWorker(Worker):
    def __init__(self, search_id: int):
        super().__init__()
        self.signals = ScrapeSignals()
        self.search_id = search_id
        self._stop = threading.Event()
        self.blocked = False
        self.tried: set[str] = set()  # websites visited in this run, whatever happened
        self.pages: dict = {}         # searches under way: query -> its pages still to come
        self.failed: set[str] = set()  # searches that failed once in this run
        self.ai_checked = 0           # leads Smart mode checked in this run

    def stop(self) -> None:
        """Finish the pages in flight, keep what is ready, then end normally (unlike
        cancel(), which goes silent)."""
        self._stop.set()

    def work(self) -> dict:
        options = searches.get(self.search_id)["options"]
        low, high = searches.leads_wanted(options)
        visiting = searches.visits_websites(options)
        searches.adopt_leads(self.search_id)
        searches.set_status(self.search_id, "running")
        ai_error, have, searched = None, 0, False
        self.client = scraper.MapsClient()
        try:
            while True:
                before = len(searches.candidates(self.search_id))
                done_before = len(searches.get(self.search_id)["progress"].get("done", []))
                searched = self.search_google(options, BATCH)
                if visiting and not self._stop.is_set():
                    self.check_websites(options)
                if options["smart"] and not self._stop.is_set() and not ai_error:
                    ai_error = self.score_with_ai(options)
                have = self.keep(options, visiting, high)
                if self._stop.is_set() or ai_error or have >= high:
                    break
                if searched:
                    # Google has nothing more for these searches: dig deeper only while
                    # under the minimum
                    if have >= low or not searches.deep_queries(self.search_id, options):
                        break
                elif len(searches.candidates(self.search_id)) == before and len(
                        searches.get(self.search_id)["progress"].get("done", [])) == done_before:
                    break  # the queries left keep failing; resuming tries them again
        finally:
            self.client.close()
        finished = searched or have >= high
        status = "done" if finished and not self._stop.is_set() and not ai_error else "stopped"
        searches.set_status(self.search_id, status)
        dropped = searches.dropped_counts(self.search_id)
        return {"status": status, "found": have, "wanted": low, "most": high,
                "blocked": self.blocked, "ai_error": ai_error, "dropped": dropped,
                "listed": len(searches.candidates(self.search_id)) + sum(dropped.values())}

    # --- step 1 -----------------------------------------------------------------
    def search_google(self, options: dict, batch: int) -> bool:
        """Fetch pages until ``batch`` more candidates fit, the searches taking turns a page
        at a time (each one's first page, then each one's second...). Searches a full batch
        cut off carry on in the next batch. True once every query is done."""
        record = searches.get(self.search_id)
        all_queries = searches.all_queries(self.search_id, options)
        done = set(record["progress"].get("done", []))
        left = [q for q in all_queries if q not in done]
        # Those under way go first, in the order they were taking turns
        waiting = deque([q for q in self.pages if q in left] +
                        [q for q in left if q not in self.pages])
        lock = threading.Lock()
        fits = searches.candidates(self.search_id)
        goal = len(fits) + batch
        state = {"finished": len(all_queries) - len(left), "total": len(all_queries),
                 "fits": len(fits), "phones": sum(bool(lead.get("phone")) for lead in fits)}
        self.signals.step.emit(1)
        self.signals.found.emit(state["fits"], state["phones"])
        self.report(state["finished"], state["total"])

        def next_page(query: str) -> list[dict] | None:
            """The query's next page, None once it has no more. Raises on errors."""
            pages = self.pages.get(query)
            if pages is None:
                pages = self.pages[query] = iter(
                    scraper.search(self.client, query, cancelled=self._stop.is_set))
            return next(pages, None)

        def run() -> None:
            while not self._stop.is_set():
                with lock:
                    if state["fits"] >= goal or not waiting:
                        return
                    query = waiting.popleft()
                try:
                    page = next_page(query)
                except scraper.Blocked:
                    self.blocked = True
                    self._stop.set()
                    return
                except (httpx.HTTPError, ValueError) as error:
                    self.pages.pop(query, None)
                    # One retry for a dropped connection; after that the query stays
                    # un-done, so resuming the search tries it again
                    if query in self.failed:
                        self.log(f"Skipped '{query}' for now: {error}", "warn")
                        continue
                    self.failed.add(query)
                    time.sleep(3)
                    with lock:
                        waiting.append(query)
                    continue
                with lock:
                    if page is None:
                        self.pages.pop(query, None)
                        searches.mark_query_done(self.search_id, query)
                        state["finished"] += 1
                        self.report(min(state["finished"], state["total"]), state["total"],
                                    query)
                        continue
                    new = searches.save_candidates(self.search_id, page, options)
                    state["fits"] += len(new)
                    state["phones"] += sum(bool(lead.get("phone")) for lead in new)
                    self.signals.found.emit(state["fits"], state["phones"])
                    waiting.append(query)  # its next page after everyone else's

        parallel = max(1, int(db.get_setting("parallel_searches", DEFAULT_PARALLEL)))
        with ThreadPoolExecutor(parallel) as pool:
            for future in [pool.submit(run) for _ in range(parallel)]:
                future.result()
        return set(all_queries) <= set(searches.get(self.search_id)["progress"].get("done", []))

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
