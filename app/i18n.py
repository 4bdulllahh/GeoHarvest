"""Text shown to the user.

shortcut: English only; t() just fills in values. The UI code copied from
HomingPigeon already routes every string through t(), so adding languages later
means swapping this module for HomingPigeon's app/i18n package.
"""


def t(text: str, **values) -> str:
    return text.format(**values) if values else text
