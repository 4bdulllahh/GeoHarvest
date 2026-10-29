"""User preferences from the Settings page."""
from __future__ import annotations

from datetime import datetime

from app.core import db

THEMES = [("Dark", "Dark"), ("Light", "Light"), ("System", "Match my computer")]
# The ready-made and home-made themes are in app.core.themes

# (key, label, scale). Scale multiplies every widget and font in the app.
TEXT_SIZES = [
    ("small", "Small", 0.9),
    ("medium", "Medium", 1.0),
    ("large", "Large", 1.15),
    ("xlarge", "Extra large", 1.3),
]

# (what the user sees, strftime pattern); the same as HomingPigeon's
DATE_FORMATS = {
    "dmy": ("DD/MM/YYYY", "%d/%m/%Y"),
    "mdy": ("MM/DD/YYYY", "%m/%d/%Y"),
    "ymd": ("YYYY-MM-DD", "%Y-%m-%d"),
    "long": ("DD Mon YYYY", "%d %b %Y"),
}
DEFAULT_DATE_FORMAT = "dmy"
TIME_FORMATS = {"12": "12-hour", "24": "24-hour"}
DEFAULT_TIME_FORMAT = "12"

DEFAULTS = {
    "appearance": "Dark",
    "text_size": "medium",
    "high_contrast": False,
    "bold_text": False,
    "smooth_scroll": True,
    "date_format": DEFAULT_DATE_FORMAT,
    "time_format": DEFAULT_TIME_FORMAT,
    "nav_order": [],          # sidebar page keys in the user's order; [] is the original order
    "nav_hidden": [],         # sidebar pages the user switched off
}
# Pages that can be moved but never hidden: without them there is no way back
ALWAYS_SHOWN = {"search"}
# What "Reset appearance" puts back
APPEARANCE_KEYS = ("appearance", "text_size", "high_contrast", "bold_text", "smooth_scroll",
                   "nav_order", "nav_hidden")


def ordered(default_keys: list[str], saved) -> list[str]:
    """The sidebar order: the saved keys that still exist, then any page added since."""
    saved = [key for key in (saved or []) if key in default_keys]
    return list(dict.fromkeys(saved)) + [key for key in default_keys if key not in saved]


def hidden_pages() -> set[str]:
    return set(get("nav_hidden") or []) - ALWAYS_SHOWN


def get(key: str):
    return db.get_setting(key, DEFAULTS[key])


def _parse(value) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def format_date(value, key: str | None = None) -> str:
    moment = _parse(value)
    if moment is None:
        return str(value or "")
    return moment.strftime(DATE_FORMATS.get(key or get("date_format"),
                                            DATE_FORMATS[DEFAULT_DATE_FORMAT])[1])


def format_time(value, seconds: bool = False, key: str | None = None) -> str:
    moment = _parse(value)
    if moment is None:
        return str(value or "")
    if (key or get("time_format")) == "24":
        return moment.strftime("%H:%M:%S" if seconds else "%H:%M")
    hour = moment.hour % 12 or 12
    rest = moment.strftime(":%M:%S" if seconds else ":%M")
    return f"{hour}{rest} {'AM' if moment.hour < 12 else 'PM'}"


def format_datetime(value, seconds: bool = False) -> str:
    moment = _parse(value)
    if moment is None:
        return str(value or "")
    return f"{format_date(moment)}  {format_time(moment, seconds)}"


def text_scale() -> float:
    wanted = get("text_size")
    for key, _label, scale in TEXT_SIZES:
        if key == wanted:
            return scale
    return 1.0
