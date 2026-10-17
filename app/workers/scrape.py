"""The search job, in three steps, each finished before the next begins:

1. Search Google: every query, page by page. Every business listed is stored as a
   candidate, with the reason it was left out if a filter rules it out.
2. Check websites (emails, social media, company age, owner), the most promising
   candidates first, until enough of them pass.
3. Pick the best: Smart mode's AI checks them in turn if it is on, then the top
   "Stop after" are kept, spread fairly over the cities and business types
   (``search.balanced``).

Everything is saved the moment it arrives and a query is only marked done once all
its pages are in, so pressing Stop, closing the app or Google pushing back loses
nothing: resuming carries on, and Stop still picks the best of what is ready.
"""
from __future__ import annotations

import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait

import httpx
from PyQt6.QtCore import pyqtSignal

from app.core import ai, db, enrich, scraper
from app.core import search as searches
from app.workers.base import Signals, Worker

DEFAULT_PARALLEL = 4
ENRICH_PARALLEL = 16  # website visits are slow to answer but cheap to wait on
POOL = 3           # with "Stop after" N, the searches share out 3N candidates to gather...
CHECK_EXTRA = 1.5  # ...and 1.5N websites are checked, so the pick has a choice


class ScrapeSignals(Signals):
    step = pyqtSignal(int)               # step 1, 2 or 3 has started
    found = pyqtSignal(int, int)         # businesses that fit so far, how many have a phone
    checked = pyqtSignal(int, int, int)  # websites checked, websites to check, emails found
    scored = pyqtSignal(int, int)        # leads the AI has checked, leads to check


class ScrapeWorker(Worker):
    def __init__(self, search_id: int):
        super().__init__()
        self.signals = ScrapeSignals()
        self.search_id = search_id
        self._stop = threading.Event()
        self.blocked = False

    def stop(self) -> None:
        """Finish the pages in flight, pick from what is ready, then end normally (unlike
        cancel(), which goes silent)."""
        self._stop.set()

    def work(self) -> dict:
        record = searches.get(self.search_id)
        options = record["options"]
        limit = int(options["max_results"] or 0)
        searches.adopt_leads(self.search_id)
        searches.set_status(self.search_id, "running")
        searched = self.search_google(record, options, limit)
        enriching = options["find_emails"] or options["find_owner"] \
            or options["company_age"] != "any"
        if enriching and not self._stop.is_set():
            self.check_websites(options, limit)
        ai_error = self.score_with_ai(options, limit) \
            if options["smart"] and not self._stop.is_set() else None
        picked = self.pick(options, limit, enriching)
        status = "done" if searched and not self._stop.is_set() and not ai_error else "stopped"
        searches.set_status(self.search_id, status)
        dropped = searches.dropped_counts(self.search_id)
        return {"status": status, "found": picked, "wanted": limit, "blocked": self.blocked,
                "ai_error": ai_error, "dropped": dropped,
                "listed": len(searches.candidates(self.search_id)) + sum(dropped.values())}

    # --- step 1 -----------------------------------------------------------------
    def search_google(self, record: dict, options: dict, limit: int) -> bool:
        """Run every query not done yet. With a limit, each stops once it has its share of
        the candidates; if they come up short, the ones that stopped carry on to the end.
        True once every query is done."""
        all_queries = searches.build_queries(options)
        done = set(record["progress"].get("done", []))
        queries = [q for q in all_queries if q not in done]
        share = math.ceil(POOL * limit / max(1, len(all_queries))) if limit else 0
        lock = threading.Lock()
        fits = searches.candidates(self.search_id)
        state = {"finished": len(all_queries) - len(queries), "total": len(all_queries),
                 "fits": len(fits), "phones": sum(bool(lead.get("phone")) for lead in fits)}
        self.signals.step.emit(1)
        self.signals.found.emit(state["fits"], state["phones"])
        self.report(state["finished"], state["total"])

        def run(query: str, share: int) -> None:
            if self._stop.is_set():
                return
            kept, full = 0, False
            for attempt in range(2):
                try:
                    for page in scraper.search(client, query, cancelled=self._stop.is_set):
                        with lock:
                            new = searches.save_candidates(self.search_id, page, options)
                            state["fits"] += len(new)
                            state["phones"] += sum(bool(lead.get("phone")) for lead in new)
                            self.signals.found.emit(state["fits"], state["phones"])
                        kept += len(new)
                        if self._stop.is_set():
                            return
                        if share and kept >= share:
                            full = True
                            break
                    break
                except scraper.Blocked:
                    self.blocked = True
                    self._stop.set()
                    return
                except (httpx.HTTPError, ValueError) as error:
                    # One retry for a dropped connection; after that the query stays
                    # un-done, so resuming the search tries it again.
                    if attempt:
                        self.log(f"Skipped '{query}' for now: {error}", "warn")
                        return
                    time.sleep(3)
            with lock:
                searches.mark_query_done(self.search_id, query, capped=full)
                state["finished"] += 1
                self.report(state["finished"], state["total"], query)

        client = scraper.MapsClient()
        parallel = int(db.get_setting("parallel_searches", DEFAULT_PARALLEL))
        try:
            with ThreadPoolExecutor(max(1, parallel)) as pool:
                list(pool.map(lambda query: run(query, share), queries))
                capped = searches.get(self.search_id)["progress"].get("capped", [])
                if limit and capped and state["fits"] < POOL * limit and not self._stop.is_set():
                    with lock:
                        state["total"] += len(capped)
                    list(pool.map(lambda query: run(query, 0), capped))
        finally:
            client.close()
        return set(all_queries) <= set(searches.get(self.search_id)["progress"].get("done", []))

    # --- step 2 -----------------------------------------------------------------
    def check_websites(self, options: dict, limit: int) -> None:
        """Visit websites, the most promising candidates first, until enough of them pass
        (the company age filter can leave some out) or none are left to check."""
        wanted_age = options["company_age"]
        enricher = enrich.Enricher(wayback=wanted_age != "any")
        lock = threading.Lock()
        fits = searches.candidates(self.search_id)
        need = math.ceil(CHECK_EXTRA * limit) if limit else len(fits)
        checked = [lead for lead in fits if lead.get("enriched")]
        state = {"checked": len(checked), "total": len(checked),
                 "emails": sum(bool(lead.get("emails")) for lead in checked)}
        tried: set[str] = set()  # each lead once per run, whatever happens to it
        self.signals.step.emit(2)
        self.signals.checked.emit(state["checked"], state["total"], state["emails"])

        def check(lead: dict) -> None:
            if self._stop.is_set():
                return
            try:
                fields = enricher.enrich(lead, options["find_emails"],
                                         find_owner=options["find_owner"])
            except Exception as error:  # noqa: BLE001 - one odd website must not end the search
                if self._stop.is_set():
                    return  # Stop cut the connection; resuming checks this site again
                self.log(f"Could not check {lead.get('website')}: {error}", "warn")
                fields = {"enriched": True}
            dropped = enrich.age_mismatch({**lead, **fields}, wanted_age)
            with lock:
                if self._stop.is_set():
                    return  # possibly half-checked when Stop cut the connection
                searches.check_candidate(self.search_id, lead["place_id"], fields, dropped)
                state["checked"] += 1
                state["emails"] += bool(fields.get("emails")) and dropped is None
                self.signals.checked.emit(state["checked"], state["total"], state["emails"])

        pool = ThreadPoolExecutor(ENRICH_PARALLEL)
        try:
            while not self._stop.is_set():
                fits = searches.candidates(self.search_id)
                passed = sum(1 for lead in fits if lead.get("enriched"))
                todo = [lead for lead in searches.balanced(fits, searches.score)
                        if not lead.get("enriched") and lead["place_id"] not in tried]
                todo = todo[:max(0, need - passed)]
                if not todo:
                    break
                tried.update(lead["place_id"] for lead in todo)
                state["total"] += len(todo)
                self.signals.checked.emit(state["checked"], state["total"], state["emails"])
                futures = [pool.submit(check, lead) for lead in todo]
                while not self._stop.is_set() and wait(futures, timeout=0.5).not_done:
                    pass
        finally:
            # Stop drops the visits still waiting or under way (closing the connections
            # cuts those short); resuming picks them up
            pool.shutdown(wait=not self._stop.is_set(), cancel_futures=True)
            enricher.close()

    # --- step 3 -----------------------------------------------------------------
    def score_with_ai(self, options: dict, limit: int) -> str | None:
        """Smart mode: the AI checks the best candidates in turn until "Stop after" of them
        reach its minimum score. Returns the error that switched it off, if one did."""
        cfg = ai.settings()
        if cfg is None:
            return None
        self.signals.step.emit(3)
        fits = [lead for lead in searches.candidates(self.search_id)
                if lead.get("enriched") or options["company_age"] == "any"]
        passed = sum("ai_score" in lead for lead in fits)
        todo = [lead for lead in searches.balanced(fits, searches.score)
                if "ai_score" not in lead]
        low = f"AI score under {cfg['min_score']}"
        done = 0
        for start in range(0, len(todo), ai.BATCH_SIZE):
            if self._stop.is_set() or (limit and passed >= limit):
                break
            batch = todo[start: start + ai.BATCH_SIZE]
            try:
                scored = ai.score(cfg, ", ".join(options["niches"]), batch)
            except ai.AIError as error:
                if error.fatal:
                    return str(error)
                self.log(str(error), "warn")
                continue
            except Exception as error:  # noqa: BLE001 - an AI hiccup must not end the search
                self.log(f"Smart mode skipped a batch: {error}", "warn")
                continue
            for lead in batch:
                fields = scored.get(lead["place_id"])
                if fields is None:
                    continue  # left unscored; resuming the search tries again
                too_low = bool(cfg["min_score"]) and fields["ai_score"] < cfg["min_score"]
                searches.check_candidate(self.search_id, lead["place_id"], fields,
                                         low if too_low else None)
                passed += not too_low
            done += len(batch)
            left = len(todo) - done
            self.signals.scored.emit(done, done + (min(left, max(0, limit - passed)) if limit
                                                   else left))
        return None

    def pick(self, options: dict, limit: int, enriching: bool) -> int:
        """Keep the best "Stop after" (or all), spread over the searches, as the leads."""
        self.signals.step.emit(3)
        fits = searches.candidates(self.search_id)
        if options["company_age"] != "any":
            fits = [lead for lead in fits if lead.get("enriched")]  # age unknown until checked

        def key(lead: dict) -> float:  # fully checked leads first (Stop leaves some unchecked)
            return (searches.score(lead) + 1000 * bool(lead.get("enriched") or not enriching)
                    + 1000 * ("ai_score" in lead or not options["smart"]))

        picked = searches.balanced(fits, key)
        picked = picked[:limit] if limit else picked
        searches.set_picked(self.search_id, picked)
        return len(picked)
