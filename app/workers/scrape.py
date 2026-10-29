"""The search job: rounds of three steps, until the minimum is reached or nothing is left.

1. Search Google: every query, page by page. Every business listed is stored as a
   candidate, with the reason it was left out if a requirement rules it out.
2. Check websites (emails, social media, company age, owner), best first, and leave
   out the ones a website requirement rules out (no email found...).
3. Smart mode's AI checks the leads left, if it is on.

Then, if fewer than "Minimum leads" meet every requirement, the next round goes
deeper: first the searches that stopped at their share carry on to the end, then
each city search Google cut short is run again in small map views
(``search.deep_queries``). Every lead that meets the requirements is kept, best
score first.

Everything is saved the moment it arrives and a query is only marked done once all
its pages are in, so pressing Stop, closing the app or Google pushing back loses
nothing: resuming carries on, and Stop still keeps what is ready.
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
POOL = 3  # with a minimum of N, the first round's searches share out 3N candidates


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

    def stop(self) -> None:
        """Finish the pages in flight, keep what is ready, then end normally (unlike
        cancel(), which goes silent)."""
        self._stop.set()

    def work(self) -> dict:
        options = searches.get(self.search_id)["options"]
        limit = int(options["min_leads"] or 0)
        visiting = searches.visits_websites(options)
        searches.adopt_leads(self.search_id)
        searches.set_status(self.search_id, "running")
        ai_error, need, first = None, 0, True
        while True:
            done_before = len(searches.get(self.search_id)["progress"].get("done", []))
            searched = self.search_google(options, limit, need, first)
            if visiting and not self._stop.is_set():
                self.check_websites(options)
            if options["smart"] and not self._stop.is_set() and not ai_error:
                ai_error = self.score_with_ai(options)
            have = self.keep(options, visiting)
            if self._stop.is_set() or ai_error or not limit or have >= limit:
                break
            need = limit - have
            progressed = first or len(searches.get(self.search_id)["progress"].get(
                "done", [])) > done_before
            first = False
            if searched and not searches.deep_queries(self.search_id, options):
                break  # every search has run to the end and been split: nothing left
            if not searched and not progressed:
                break  # the queries left keep failing; resuming tries them again
        finished = searched or (limit and have >= limit)
        status = "done" if finished and not self._stop.is_set() and not ai_error else "stopped"
        searches.set_status(self.search_id, status)
        dropped = searches.dropped_counts(self.search_id)
        return {"status": status, "found": have, "wanted": limit, "blocked": self.blocked,
                "ai_error": ai_error, "dropped": dropped,
                "listed": len(searches.candidates(self.search_id)) + sum(dropped.values())}

    # --- step 1 -----------------------------------------------------------------
    def search_google(self, options: dict, limit: int, need: int, first: bool) -> bool:
        """Run every query not done yet. With a minimum, the first round's queries each stop
        once they have their share of the candidates; later rounds run those to the end,
        then the deeper ones, starting no more once there are enough candidates (the rest
        wait for another round, or for resuming). True once every query is done."""
        record = searches.get(self.search_id)
        all_queries = searches.all_queries(self.search_id, options)
        done = set(record["progress"].get("done", []))
        capped = [] if first else record["progress"].get("capped", [])
        queries = capped + [q for q in all_queries if q not in done]
        share = math.ceil(POOL * limit / max(1, len(all_queries))) if limit and first else 0
        lock = threading.Lock()
        fits = searches.candidates(self.search_id)
        goal = len(fits) + POOL * need if need and not first else 0  # 0: no goal
        state = {"finished": len(all_queries) - len(queries), "total": len(all_queries),
                 "fits": len(fits), "phones": sum(bool(lead.get("phone")) for lead in fits)}
        self.signals.step.emit(1)
        self.signals.found.emit(state["fits"], state["phones"])
        self.report(max(0, state["finished"]), state["total"])

        def run(query: str) -> None:
            if self._stop.is_set() or (goal and state["fits"] >= goal):
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
                self.report(min(state["finished"], state["total"]), state["total"], query)

        client = scraper.MapsClient()
        parallel = int(db.get_setting("parallel_searches", DEFAULT_PARALLEL))
        try:
            with ThreadPoolExecutor(max(1, parallel)) as pool:
                list(pool.map(run, queries))
        finally:
            client.close()
        return set(all_queries) <= set(searches.get(self.search_id)["progress"].get("done", []))

    # --- step 2 -----------------------------------------------------------------
    def check_websites(self, options: dict) -> None:
        """Visit the website of every candidate not checked yet, best first, and leave out
        the ones a website requirement (age, email, social media...) rules out."""
        enricher = enrich.Enricher(wayback=searches.age_filtered(options))
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
                                         find_owner=options["find_owner"])
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

        pool = ThreadPoolExecutor(ENRICH_PARALLEL)
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
                       if "ai_score" not in lead and (lead.get("enriched") or not visiting)),
                      key=searches.score, reverse=True)
        low = f"AI score under {cfg['min_score']}"
        for start in range(0, len(todo), ai.BATCH_SIZE):
            if self._stop.is_set():
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
            self.signals.scored.emit(min(start + len(batch), len(todo)), len(todo))
        return None

    def keep(self, options: dict, visiting: bool) -> int:
        """Make every candidate that meets the requirements a lead, best first: fully checked
        ones before any Stop left unchecked, known company ages before unknown ones."""
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
                    "age_years" in lead or not searches.age_filtered(options),
                    searches.score(lead))

        kept = sorted(fits, key=key, reverse=True)
        searches.set_picked(self.search_id, kept)
        self.signals.leads.emit(len(kept))
        return len(kept)
