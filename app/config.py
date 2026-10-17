"""Application paths and constants."""
import os
import sys
from pathlib import Path

APP_NAME = "GeoHarvest"
APP_TITLE = "GeoHarvest"
APP_VERSION = "v0.1.3 beta"
APP_TAGLINE = "Find business leads on Google Maps"
REPO_URL = "https://github.com/4bdulllahh/GeoHarvest"


def _app_data_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    return Path(base) / APP_NAME


DATA_DIR = _app_data_dir()
DB_PATH = DATA_DIR / "geoharvest.db"
SECRETS_PATH = DATA_DIR / "secrets.dat"
EXPORTS_DIR = DATA_DIR / "exports"
LOGS_DIR = DATA_DIR / "logs"


def ensure_dirs() -> None:
    for d in (DATA_DIR, EXPORTS_DIR, LOGS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def resource_path(relative: str) -> Path:
    """Resolve a bundled resource, working both from source and from a PyInstaller build."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / relative
    return Path(__file__).resolve().parent.parent / relative
