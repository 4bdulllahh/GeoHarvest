"""Shared by every test file."""
import pytest

from app import config


@pytest.fixture(autouse=True)
def own_logs(tmp_path, monkeypatch):
    """Errors raised on purpose in tests go to a throwaway crash.log, not the user's."""
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
    (tmp_path / "logs").mkdir()
