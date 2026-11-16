"""Excel and CSV export.

Only columns that have a value in at least one lead are written, so a quick-mode
export has no empty AI columns. Text from Google is untrusted: a business named
"=HYPERLINK(...)" must reach the sheet as text, never as a formula.
"""
from __future__ import annotations

import csv
import json
import math
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.core.places import FIELDS, NOT_FOUND

LINK_COLUMNS = {"website", "maps_url", "reviews_url", "facebook", "instagram", "linkedin",
                "twitter", "youtube", "tiktok", "photo", "owner_linkedin"}
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")  # Excel refuses these outright
# What a spreadsheet can't work out as a sum: a plain number ("-73.98", "+97145550100"), or
# a phone number with a space after its country code ("+1 212-555-0100"). "+1-1" is a sum.
_PHONE = re.compile(r"^(?:[+-][\d.]+|\+\d+\s\(?\d[\d\s().-]*)$")
EXCEL_CELL_LIMIT = 32767


@contextmanager
def _finished(path: Path) -> Iterator[Path]:
    """A name to write to first. Only a file written to the end takes ``path``'s place, so
    an export that fails never leaves half a file or spoils the one already there."""
    path = Path(path)
    part = path.with_name(path.name + ".part")
    try:
        yield part
        os.replace(part, path)
    finally:
        part.unlink(missing_ok=True)


def columns_in_use(leads: list[dict], keys: list[str] | None = None) -> list[tuple[str, str]]:
    """Columns with a value somewhere, limited to ``keys`` (the ones on screen) if given."""
    return [(key, header) for key, header in FIELDS
            if (keys is None or key in keys)
            and any(lead.get(key) not in (None, "", []) for lead in leads)]


def _text(value) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return ""
    if isinstance(value, (list, tuple)):
        value = ", ".join(_text(item) for item in value)
    elif isinstance(value, dict):
        value = json.dumps(value, ensure_ascii=False, default=str)
    return _CONTROL.sub("", str(value))[:EXCEL_CELL_LIMIT]


def safe_csv(value) -> str:
    """Stop spreadsheet apps treating a cell as a formula; phone numbers stay as they are."""
    text = _text(value)
    start = text.lstrip()  # a tab or a new line in front does not stop a formula
    if start[:1] in ("=", "@") or (start[:1] in ("+", "-") and not _PHONE.match(start)):
        return "'" + text
    return text


def to_csv(leads: list[dict], path: Path, keys: list[str] | None = None) -> int:
    columns = columns_in_use(leads, keys)
    # utf-8-sig: the byte-order mark is what makes Excel read accents and Arabic correctly
    with _finished(path) as part, open(part, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow([header for _key, header in columns])
        for lead in leads:
            writer.writerow([safe_csv(lead.get(key)) for key, _header in columns])
    return len(leads)


def to_xlsx(leads: list[dict], path: Path, keys: list[str] | None = None) -> int:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    columns = columns_in_use(leads, keys)
    book = Workbook()
    sheet = book.active
    sheet.title = "Leads"
    sheet.append([header for _key, header in columns])
    header_fill = PatternFill("solid", fgColor="2B5F96")
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill

    link_font = Font(color="0563C1", underline="single")
    for row_number, lead in enumerate(leads, start=2):
        for col_number, (key, _header) in enumerate(columns, start=1):
            value = lead.get(key)
            if (isinstance(value, (int, float)) and not isinstance(value, bool)
                    and math.isfinite(value)):  # "not a number" makes Excel repair the file
                sheet.cell(row_number, col_number, value)
                continue
            text = _text(value)
            cell = sheet.cell(row_number, col_number)
            cell.value = text
            cell.data_type = "s"  # never a formula, whatever the text starts with
            if key in LINK_COLUMNS and text.startswith(("http://", "https://")):
                cell.hyperlink = text
                cell.font = link_font

    for col_number, (key, header) in enumerate(columns, start=1):
        sample = [len(_text(lead.get(key))) for lead in leads[:200]]
        width = max([len(header)] + sample) + 2
        sheet.column_dimensions[get_column_letter(col_number)].width = min(max(width, 8), 50)
    sheet.freeze_panes = "B2"
    sheet.auto_filter.ref = sheet.dimensions
    with _finished(path) as part:
        book.save(part)
    return len(leads)


# CRM imports: each CRM's own column names for a company (account, organization), so its
# import screen matches them up by itself. "first_email" is the business's first email.
CRMS = {
    "hubspot": ("HubSpot", [
        ("Company name", "name"), ("Company domain name", "domain"), ("Website URL", "website"),
        ("Phone number", "phone"), ("Email", "first_email"), ("Street address", "street"),
        ("City", "city"), ("State/Region", "state"), ("Postal code", "postal_code"),
        ("Country/Region", "country_code"), ("Description", "description"),
        ("Contact name", "owner_name"), ("LinkedIn company page", "linkedin"),
        ("Facebook company page", "facebook"), ("Google Maps link", "maps_url")]),
    "pipedrive": ("Pipedrive", [
        ("Organization - Name", "name"), ("Organization - Address", "address"),
        ("Organization - Website", "website"), ("Person - Name", "owner_name"),
        ("Person - Email", "first_email"), ("Person - Phone", "phone"),
        ("Note - Content", "category")]),
    "zoho": ("Zoho CRM", [
        ("Account Name", "name"), ("Phone", "phone"), ("Website", "website"),
        ("Email", "first_email"), ("Industry", "category"), ("Billing Street", "street"),
        ("Billing City", "city"), ("Billing State", "state"), ("Billing Code", "postal_code"),
        ("Billing Country", "country_code"), ("Description", "description"),
        ("Contact Name", "owner_name"), ("Rating", "rating")]),
    "salesforce": ("Salesforce", [
        ("Account Name", "name"), ("Phone", "phone"), ("Website", "website"),
        ("Industry", "category"), ("Billing Street", "street"), ("Billing City", "city"),
        ("Billing State/Province", "state"), ("Billing Zip/Postal Code", "postal_code"),
        ("Billing Country", "country_code"), ("Description", "description"),
        ("Email", "first_email"), ("Contact Name", "owner_name")]),
    # One row per email, in the columns HomingPigeon's import recognises; the rest
    # become mail-merge variables there ({City}, {Category}...)
    "homingpigeon": ("HomingPigeon", [
        ("Email", "first_email"), ("Company", "name"), ("Contact person", "owner_name"),
        ("City", "city"), ("Category", "category"), ("Website", "website"),
        ("Phone", "phone"), ("Rating", "rating"), ("Reviews", "reviews"),
        ("Google Maps link", "maps_url")]),
}
ONE_ROW_PER_EMAIL = {"homingpigeon"}


def email_list(lead: dict) -> list[str]:
    emails = lead.get("emails") or ""
    if not isinstance(emails, (list, tuple)):
        emails = str(emails).split(",")
    return [email.strip() for email in map(str, emails) if email.strip()]


def _crm_value(lead: dict, key: str):
    if key == "first_email":
        return next(iter(email_list(lead)), "")
    if key == "street" and not lead.get("street"):
        return lead.get("address")  # some countries' addresses have no street part
    return None if lead.get(key) == NOT_FOUND else lead.get(key)  # CRMs expect a link there


def to_crm(leads: list[dict], path: Path, crm: str) -> int:
    columns = CRMS[crm][1]
    with _finished(path) as part, open(part, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow([header for header, _key in columns])
        if crm in ONE_ROW_PER_EMAIL:
            leads = [dict(lead, emails=email) for lead in leads for email in email_list(lead)]
        for lead in leads:
            writer.writerow([safe_csv(_crm_value(lead, key)) for _header, key in columns])
    return len(leads)


def to_tsv(leads: list[dict], keys: list[str] | None = None) -> str:
    """Tab-separated text for pasting into Google Sheets (which reads it as cells)."""
    columns = columns_in_use(leads, keys)
    rows = [[header for _key, header in columns]]
    # Sheets reads a pasted "+971..." as a formula; a leading ' keeps it text and is not shown
    rows += [["'" + text if (text := " ".join(_text(lead.get(key)).split())).startswith(
        ("=", "+", "-", "@")) else text for key, _header in columns] for lead in leads]
    return "\n".join("\t".join(row) for row in rows)


def export(leads: list[dict], path: Path, keys: list[str] | None = None) -> int:
    path = Path(path)
    return (to_csv if path.suffix.lower() == ".csv" else to_xlsx)(leads, path, keys)
