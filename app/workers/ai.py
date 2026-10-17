"""Smart mode on demand: score a saved search's leads with the user's AI (Leads page)."""
from __future__ import annotations

from PyQt6.QtCore import pyqtSignal

from app.core import ai
from app.core import search as searches
from app.workers.base import Signals, Worker


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
