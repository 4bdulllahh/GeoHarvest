"""User preferences from the Settings page."""
from __future__ import annotations

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

DEFAULTS = {
    "appearance": "Dark",
    "text_size": "medium",
    "high_contrast": False,
    "bold_text": False,
    "smooth_scroll": True,
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


def text_scale() -> float:
    wanted = get("text_size")
    for key, _label, scale in TEXT_SIZES:
        if key == wanted:
            return scale
    return 1.0
