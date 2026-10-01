"""Satrix 40 rebalancing notices from JSE SENS: saved by hand from the JSE's site, then parsed for every constituent's weights."""

import io
import re
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader

FILE_NAME = re.compile(r"SENS_(\d{8})_(S\d+)\.pdf$", re.I)
# A row's weights can wrap onto the next lines (Prosus in September 2023), so rows are matched across line breaks
ROW = re.compile(r"^\s*([A-Z0-9]{2,5})\s+([^%\n]+?)\s+(\d{1,3}\.\d{2})%\s+(\d{1,3}\.\d{2})%", re.M)
# Both totals on one line; a wrapped row can leave two weights on lines of their own
TOTAL = re.compile(r"^[ \t]*(\d{1,3}\.\d{2})%[ \t]+(\d{1,3}\.\d{2})%[ \t]*$", re.M)
DATE = r"(\d{1,2} [A-Z][a-z]+ \d{4})"


class UnparsedNotice(ValueError):
    pass


class NotSatrix40(ValueError):
    pass


def identify(path: Path) -> tuple[str, str]:
    found = FILE_NAME.search(path.name)
    if not found:
        raise UnparsedNotice(f"{path.name} is not named like a SENS PDF (SENS_YYYYMMDD_Snnnnnn.pdf)")
    return datetime.strptime(found.group(1), "%Y%m%d").date().isoformat(), found.group(2).upper()


def extract(pdf: bytes) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)


def iso(text: str) -> str:
    return datetime.strptime(text, "%d %B %Y").date().isoformat()


def weight(text: str) -> float:
    return round(float(text) / 100, 6)


def parse_text(text: str) -> dict:
    code = re.search(r"JSE code:\s*([A-Z0-9]+)", text, re.I)
    if not code or code.group(1) != "STX40":
        raise NotSatrix40(f"JSE code {code.group(1) if code else 'missing'}, not STX40")
    flat = " ".join(text.split())  # dates can break across lines
    # Satrix sometimes misplaces the comma: "effective from , Thursday 26 September 2024"
    effective = re.search(rf"effective\s+from\s*,?\s*\w+,?\s*{DATE}", flat, re.I)
    applied = re.search(rf"after\s+the\s+close\s+of\s+business\s+on\s+\w+,?\s*{DATE}", flat, re.I)
    if not effective:
        raise UnparsedNotice("no effective date found")
    total = TOTAL.search(text)  # the main table ends at its totals; the added and removed lists follow
    if not total:
        raise UnparsedNotice("no totals line found")
    # Columns are previous then new, as the added and removed lists confirm
    rows = [{"code": r.group(1), "name": r.group(2).strip(), "previous": weight(r.group(3)), "new": weight(r.group(4))}
            for r in ROW.finditer(text[:total.start()])]
    if not rows:
        raise UnparsedNotice("no constituent table found")
    return {"effective_date": iso(effective.group(1)), "applied_after": iso(applied.group(1)) if applied else None,
            "constituents": rows, "printed_totals": (weight(total.group(1)), weight(total.group(2)))}


def parse(pdf: bytes) -> dict:
    return parse_text(extract(pdf))
