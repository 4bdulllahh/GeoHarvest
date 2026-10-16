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

from app.core import db, enrich, scraper
from app.core import search as searches
from app.workers.base import Signals, Worker

DEFAULT_PARALLEL = 4
ENRICH_PARALLEL = 16  # website visits are slow to answer but cheap to wait on


class ScrapeSignals(Signals):
    leads = pyqtSignal(list)            # newly saved leads, for the live table
    updated = pyqtSignal(str, dict)     # place id, fields added by enrichment
    removed = pyqtSignal(str)           # place id dropped by the company age filter
    checked = pyqtSignal(int, int)      # websites checked, websites to check


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
        lock = threading.Lock()
        state = {"finished": len(all_queries) - len(queries), "found": searches.count(self.search_id)}
        searches.set_status(self.search_id, "running")
        self.report(state["finished"], len(all_queries), "Starting")

        def stopping() -> bool:
            return self._stop.is_set() or (limit and state["found"] >= limit)

        # --- enrichment: runs alongside the search, fed as leads are saved ----
        wants_age = options["company_age"] != "any"
        enricher = enrich.Enricher(wayback=wants_age) if options["find_emails"] or wants_age             else None
        enrich_pool = ThreadPoolExecutor(ENRICH_PARALLEL) if enricher else None
        checks = {"done": 0, "total": 0}

        def enrich_one(lead: dict) -> None:
            if self._stop.is_set():
                return
            try:
                fields = enricher.enrich(lead, options["find_emails"])
            except Exception as error:  # noqa: BLE001 - one odd website must not end the search
                self.log(f"Could not check {lead.get('website')}: {error}", "warn")
                fields = {"enriched": True}
            with lock:
                if enrich.matches_age({**lead, **fields}, options["company_age"]):
                    searches.update_lead(self.search_id, lead["place_id"], fields)
                    self.signals.updated.emit(lead["place_id"], fields)
                else:
                    searches.remove_lead(self.search_id, lead["place_id"])
                    self.signals.removed.emit(lead["place_id"])
                checks["done"] += 1
                self.signals.checked.emit(checks["done"], checks["total"])

        def queue_enrichment(leads: list[dict]) -> None:
            if enrich_pool is None:
                return
            with lock:
                checks["total"] += len(leads)
            for lead in leads:
                enrich_pool.submit(enrich_one, lead)

        # Resuming: leads saved last time but never checked
        queue_enrichment([lead for lead in searches.leads(self.search_id)
                          if not lead.get("enriched")])

        def run(query: str) -> None:
            if stopping():
                return
            for attempt in range(2):
                try:
                    for page in scraper.search(client, query, cancelled=stopping):
                        keep = [lead for lead in page if searches.passes(lead, options)]
                        with lock:
                            if limit:
                                keep = keep[: max(0, limit - state["found"])]
                            saved = searches.save_leads(self.search_id, keep, options["skip_known"])
                            state["found"] += len(saved)
                        if saved:
                            self.signals.leads.emit(saved)
                            queue_enrichment(saved)
                        if stopping():
                            return
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
                # Stop drops the website visits still waiting; resume picks them up
                enrich_pool.shutdown(wait=True, cancel_futures=self._stop.is_set())
        finally:
            client.close()
            if enricher is not None:
                enricher.close()

        searched = state["finished"] == len(all_queries) or (limit and state["found"] >= limit)
        complete = searched and checks["done"] == checks["total"]
        status = "done" if complete and not self.blocked else "stopped"
        searches.set_status(self.search_id, status)
        return {"status": status, "found": state["found"], "blocked": self.blocked}
