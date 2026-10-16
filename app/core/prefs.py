"""User preferences from the Settings page."""
from __future__ import annotations

from app.core import db

THEMES = [("Dark", "Dark"), ("Light", "Light"), ("System", "Match my computer")]

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
}


def get(key: str):
    return db.get_setting(key, DEFAULTS[key])


def text_scale() -> float:
    wanted = get("text_size")
    for key, _label, scale in TEXT_SIZES:
        if key == wanted:
            return scale
    return 1.0
