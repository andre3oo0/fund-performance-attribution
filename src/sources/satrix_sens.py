"""Satrix 40 rebalancing notices from JSE SENS: saved by hand from the JSE's site, then parsed for every constituent's weights."""

import io
import re
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader

FILE_NAME = re.compile(r"SENS_(\d{8})_(S\d+)\.pdf$", re.I)
ROW = re.compile(r"^\s*([A-Z0-9]{2,5})\s+(.+?)\s+(\d{1,3}\.\d{2})%\s+(\d{1,3}\.\d{2})%\s*$")
TOTAL = re.compile(r"^\s*(\d{1,3}\.\d{2})%\s+(\d{1,3}\.\d{2})%\s*$")
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


def parse_text(text: str) -> dict:
    code = re.search(r"JSE Code:\s*([A-Z0-9]+)", text)
    if not code or code.group(1) != "STX40":
        raise NotSatrix40(f"JSE code {code.group(1) if code else 'missing'}, not STX40")
    effective = re.search(rf"effective\s+from\s+\w+,\s*{DATE}", text, re.I)
    applied = re.search(rf"after\s+the\s+close\s+of\s+business\s+on\s+\w+,\s*{DATE}", text, re.I)
    if not effective:
        raise UnparsedNotice("no effective date found")
    rows, totals = [], None
    for line in text.splitlines():
        if totals is None and (row := ROW.match(line)):
            rows.append({"code": row.group(1), "name": row.group(2).strip(),
                         "previous": round(float(row.group(3)) / 100, 6), "new": round(float(row.group(4)) / 100, 6)})
        elif totals is None and rows and (total := TOTAL.match(line)):
            totals = (round(float(total.group(1)) / 100, 6), round(float(total.group(2)) / 100, 6))  # the main table ends at its totals
    if not rows or totals is None:
        raise UnparsedNotice("no constituent table with totals found")
    return {"effective_date": iso(effective.group(1)), "applied_after": iso(applied.group(1)) if applied else None,
            "constituents": rows, "printed_totals": totals}


def parse(pdf: bytes) -> dict:
    return parse_text(extract(pdf))
