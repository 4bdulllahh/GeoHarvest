"""Smart mode jobs: score leads with the user's AI, a batch at a time."""
from __future__ import annotations

import queue
import threading
from typing import Callable

from PyQt6.QtCore import pyqtSignal

from app.core import ai
from app.core import search as searches
from app.workers.base import Signals, Worker


class AIStage:
    """Scores leads on its own thread while a search is still finding more.

    Leads are put in one at a time; they go to the AI in batches of
    ``ai.BATCH_SIZE``, or sooner if no new lead has arrived for two seconds.
    A fatal error (wrong key, unknown model) switches the stage off: the
    remaining leads stay unscored, and resuming the search tries them again.
    """

    def __init__(self, cfg: dict, searched_for: str,
                 on_scored: Callable[[list[dict], dict[str, dict]], None],
                 on_error: Callable[[str], None]):
        self.cfg = cfg
        self.searched_for = searched_for
        self.on_scored = on_scored
        self.on_error = on_error
        self.failed: str | None = None
        self._queue: queue.Queue = queue.Queue()
        self._stopped = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def put(self, lead: dict) -> None:
        self._queue.put(lead)

    def close(self, cancel: bool = False) -> None:
        """Score what is queued (or drop it, if ``cancel``), then end the thread."""
        if cancel:
            self._stopped.set()
        self._queue.put(None)
        self._thread.join()

    def _run(self) -> None:
        batch: list[dict] = []
        while True:
            try:
                item = self._queue.get(timeout=2 if batch else None)
            except queue.Empty:
                item = "flush"
            if isinstance(item, dict):
                batch.append(item)
            if batch and (item is None or item == "flush" or len(batch) >= ai.BATCH_SIZE):
                self._score(batch)
                batch = []
            if item is None:
                return

    def _score(self, batch: list[dict]) -> None:
        if self._stopped.is_set():
            return
        try:
            scored = ai.score(self.cfg, self.searched_for, batch)
        except ai.AIError as error:
            if error.fatal:
                self.failed = str(error)
                self._stopped.set()
            self.on_error(str(error))
            return
        except Exception as error:  # noqa: BLE001 - an AI hiccup must not end the search
            self.on_error(f"Smart mode skipped a batch: {error}")
            return
        self.on_scored(batch, scored)


class ScoreSignals(Signals):
    updated = pyqtSignal(str, dict)   # place id, AI fields


class AIScoreWorker(Worker):
    """Score the leads of a saved search on demand (the Leads page's button)."""

    def __init__(self, search_id: int, leads: list[dict]):
        super().__init__()
        self.signals = ScoreSignals()
        self.search_id = search_id
        self.leads = leads

    def work(self) -> dict:
        cfg = ai.settings()
        if cfg is None:
            raise ai.AIError("Set up Smart mode first.")
        searched_for = ", ".join(searches.get(self.search_id)["options"]["niches"])
        done = scored_count = 0
        for start in range(0, len(self.leads), ai.BATCH_SIZE):
            if self.cancelled:
                break
            batch = self.leads[start: start + ai.BATCH_SIZE]
            try:
                scored = ai.score(cfg, searched_for, batch)
            except ai.AIError as error:
                if error.fatal:
                    raise
                self.log(str(error), "warn")
                scored = {}
            for place_id, fields in scored.items():
                searches.update_lead(self.search_id, place_id, fields)
                self.signals.updated.emit(place_id, fields)
            done += len(batch)
            scored_count += len(scored)
            self.report(done, len(self.leads), "")
        return {"scored": scored_count}
