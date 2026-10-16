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

from app.core import db, scraper
from app.core import search as searches
from app.workers.base import Signals, Worker

DEFAULT_PARALLEL = 4


class ScrapeSignals(Signals):
    leads = pyqtSignal(list)  # newly saved leads, for the live table


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
        finally:
            client.close()

        complete = state["finished"] == len(all_queries) or (limit and state["found"] >= limit)
        status = "done" if complete and not self.blocked else "stopped"
        searches.set_status(self.search_id, status)
        return {"status": status, "found": state["found"], "blocked": self.blocked}
