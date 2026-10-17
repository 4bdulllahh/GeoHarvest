"""The search job: run every query of a search, a few at a time, saving as it goes.

Every page of results is written to the database the moment it arrives, and a
query is only marked done once all its pages are in. Closing the app, pressing
Stop or Google pushing back therefore loses nothing: resuming runs only the
queries that are not marked done.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
from PyQt6.QtCore import pyqtSignal

from app.core import ai, db, enrich, scraper
from app.core import search as searches
from app.workers.ai import AIStage
from app.workers.base import Signals, Worker

DEFAULT_PARALLEL = 4
ENRICH_PARALLEL = 16  # website visits are slow to answer but cheap to wait on


class ScrapeSignals(Signals):
    leads = pyqtSignal(list)            # newly saved leads, for the live table
    updated = pyqtSignal(str, dict)     # place id, fields added by enrichment
    removed = pyqtSignal(str)           # place id dropped by the company age filter
    checked = pyqtSignal(int, int)      # websites checked, websites to check
    scored = pyqtSignal(int, int)       # leads the AI has checked, leads to check


class ScrapeWorker(Worker):
    def __init__(self, search_id: int):
        super().__init__()
        self.signals = ScrapeSignals()
        self.search_id = search_id
        self._stop = threading.Event()
        self.blocked = False

    def stop(self) -> None:
        """Finish the pages in flight, then end normally (unlike cancel(), which goes silent)."""
        self._stop.set()

    def work(self) -> dict:
        record = searches.get(self.search_id)
        options = record["options"]
        all_queries = searches.build_queries(options)
        done = set(record["progress"].get("done", []))
        queries = [q for q in all_queries if q not in done]
        limit = int(options["max_results"] or 0)
        lock = threading.RLock()
        # found: leads kept so far; the age filter and Smart mode can still take some away
        state = {"finished": len(all_queries) - len(queries), "found": searches.count(self.search_id)}
        searches.set_status(self.search_id, "running")
        self.report(state["finished"], len(all_queries), "Starting")

        def room() -> int:
            """How many more leads "Stop after" allows. While that is none but saved leads
            are still being checked (and may be dropped), wait to see how many stay."""
            while True:
                with lock:
                    free = limit - state["found"]
                    busy = checks["total"] - checks["done"] + (stage.pending if stage else 0)
                if free > 0 or not busy or self._stop.is_set():
                    return free
                time.sleep(0.5)

        def stopping() -> bool:
            return self._stop.is_set() or bool(limit and room() <= 0)

        # --- enrichment: runs alongside the search, fed as leads are saved ----
        wants_age = options["company_age"] != "any"
        enricher = enrich.Enricher(wayback=wants_age) \
            if options["find_emails"] or options["find_owner"] or wants_age else None
        enrich_pool = ThreadPoolExecutor(ENRICH_PARALLEL) if enricher else None
        checks = {"done": 0, "total": 0}

        def enrich_one(lead: dict) -> None:
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
            keep = enrich.matches_age({**lead, **fields}, options["company_age"])
            with lock:
                if self._stop.is_set():
                    return  # possibly half-checked when Stop cut the connection
                if keep:
                    searches.update_lead(self.search_id, lead["place_id"], fields)
                    self.signals.updated.emit(lead["place_id"], fields)
                    queue_scoring({**lead, **fields})
                else:
                    searches.remove_lead(self.search_id, lead["place_id"])
                    self.signals.removed.emit(lead["place_id"])
                    state["found"] -= 1
                checks["done"] += 1
                self.signals.checked.emit(checks["done"], checks["total"])

        def queue_enrichment(leads: list[dict]) -> None:
            if enrich_pool is None:
                for lead in leads:
                    queue_scoring(lead)
                return
            with lock:
                checks["total"] += len(leads)
            for lead in leads:
                enrich_pool.submit(enrich_one, lead)

        # --- smart mode: the AI scores each lead once its details are complete ---
        cfg = ai.settings() if options["smart"] else None
        min_score = cfg["min_score"] if cfg else 0
        scores = {"done": 0, "total": 0}

        def on_scored(batch: list[dict], scored: dict[str, dict]) -> None:
            with lock:
                for lead in batch:
                    fields = scored.get(lead["place_id"])
                    if fields is None:
                        continue  # left unscored; resuming the search tries again
                    if min_score and fields["ai_score"] < min_score:
                        searches.remove_lead(self.search_id, lead["place_id"])
                        self.signals.removed.emit(lead["place_id"])
                        state["found"] -= 1
                    else:
                        searches.update_lead(self.search_id, lead["place_id"], fields)
                        self.signals.updated.emit(lead["place_id"], fields)
                scores["done"] += len(batch)
                self.signals.scored.emit(scores["done"], scores["total"])

        stage = AIStage(cfg, ", ".join(options["niches"]), on_scored,
                        lambda message: self.log(message, "warn")) if cfg else None

        def queue_scoring(lead: dict) -> None:
            if stage is None:
                return
            with lock:
                scores["total"] += 1
            stage.put(lead)

        # Resuming: leads saved last time but never checked or never scored
        unchecked = []
        for lead in searches.leads(self.search_id):
            if enrich_pool is not None and not lead.get("enriched"):
                unchecked.append(lead)
            elif "ai_score" not in lead:
                queue_scoring(lead)
        queue_enrichment(unchecked)

        def run(query: str) -> None:
            if stopping():
                return
            for attempt in range(2):
                try:
                    for page in scraper.search(client, query, cancelled=self._stop.is_set):
                        waiting = [lead for lead in page if searches.passes(lead, options)]
                        while True:
                            with lock:
                                keep = waiting[: max(0, limit - state["found"])] if limit \
                                    else waiting
                                waiting = waiting[len(keep):]
                                saved = searches.save_leads(self.search_id, keep,
                                                            options["skip_known"])
                                state["found"] += len(saved)
                                if saved:  # queued under the lock so room() never misses them
                                    self.signals.leads.emit(saved)
                                    queue_enrichment(saved)
                            if stopping():
                                return
                            if not waiting:  # else checks freed room: save the rest of the page
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
                searches.mark_query_done(self.search_id, query)
                state["finished"] += 1
            self.report(state["finished"], len(all_queries), query)

        client = scraper.MapsClient()
        parallel = int(db.get_setting("parallel_searches", DEFAULT_PARALLEL))
        try:
            with ThreadPoolExecutor(max(1, parallel)) as pool:
                list(pool.map(run, queries))
            if enrich_pool is not None:
                # Stop drops the website visits still waiting or under way (closing the
                # connection below cuts those short); resume picks them up
                enrich_pool.shutdown(wait=not self._stop.is_set(),
                                     cancel_futures=self._stop.is_set())
            if stage is not None:
                stage.close(cancel=self._stop.is_set())
        finally:
            client.close()
            if enricher is not None:
                enricher.close()

        searched = state["finished"] == len(all_queries) or (limit and state["found"] >= limit)
        ai_error = stage.failed if stage is not None else None
        complete = searched and checks["done"] == checks["total"] \
            and scores["done"] == scores["total"] and not ai_error
        status = "done" if complete and not self.blocked else "stopped"
        searches.set_status(self.search_id, status)
        return {"status": status, "found": state["found"], "blocked": self.blocked,
                "ai_error": ai_error}
