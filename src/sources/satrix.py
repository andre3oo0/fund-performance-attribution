"""Satrix 40 annual financial statements: fetched as PDF bytes, and their holdings, totals and industry tables parsed."""

import io
import re
import time

import requests
from pypdf import PdfReader

try:
    import truststore  # uses the operating system's certificate store; verification stays on

    truststore.inject_into_ssl()
except ImportError:
    pass

NUM = r"\d{1,3}(?: \d{3})*"
HOLDING = rf"({NUM})\s+([\d,]+\.\d+)\s+({NUM})\s+(\d+\.\d)%"
EMPTY = r"-\s+-\s+-\s+0\.0%"
# ICB industries as Satrix prints them; Consumer Goods and Consumer Services are the pre-2021 ICB structure
SECTORS = ["Basic Materials", "Consumer Discretion", "Consumer Goods", "Consumer Services", "Consumer Staples",
           "Energy", "Financials", "Health Care", "Industrials", "Real Estate", "Technology", "Telecommunications",
           "Utilities"]


class UnparsedStatement(ValueError):
    pass


def fetch(url: str, attempts: int = 4) -> bytes:
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(url, headers={"User-Agent": "fund-performance-attribution"}, timeout=120)
            response.raise_for_status()
            break
        except requests.ConnectionError:  # Satrix's server resets some connections from cloud runners
            if attempt == attempts:
                raise
            time.sleep(15 * attempt)
    if not response.content.startswith(b"%PDF"):
        raise UnparsedStatement(f"{url} did not return a PDF")
    return response.content


def extract(pdf: bytes) -> tuple[str, list[str]]:
    reader = PdfReader(io.BytesIO(pdf))
    plain = "\n".join(page.extract_text() or "" for page in reader.pages)
    return plain, [page.extract_text(extraction_mode="layout") for page in reader.pages]


def number(text: str) -> float:
    return float(text.replace(" ", "").replace(",", ""))


def holding(match: re.Match, offset: int = 0) -> dict:
    shares, price, value, weight = (match.group(offset + i) for i in range(1, 5))
    return {"shares": number(shares), "price": number(price), "fair_value": number(value), "weight": number(weight) / 100}


def year_end(text: str) -> int:
    found = re.search(r"(?:year|period) ended 31 December (\d{4})", text, re.I)
    if not found:
        raise UnparsedStatement("no year-end found")
    return int(found.group(1))


def holdings_on(layout: str, year: int) -> list[dict]:
    header = next(l for l in layout.splitlines() if "No. of shares" in l)
    split = header.rfind("No. of shares") - 4  # a figure starting right of here belongs to the prior year
    found = []
    for line in layout.splitlines():
        body = line.strip()
        both = re.match(rf"^(.+?)\s{{2,}}(?:{HOLDING}|{EMPTY})\s+(?:{HOLDING}|{EMPTY})\s*$", body)
        one = re.match(rf"^(.+?)\s{{2,}}{HOLDING}\s*$", body)
        if both:
            name = both.group(1).strip()
            if both.group(2):
                found.append({"name": name, "year": year, **holding(both, 1)})
            if both.group(6):
                found.append({"name": name, "year": year - 1, **holding(both, 5)})
        elif one and not re.search(r"\d%\s", body[:len(one.group(1)) + 1]):
            name = one.group(1).strip()
            starts = line.index(one.group(2), line.index(name) + len(name))
            found.append({"name": name, "year": year - 1 if starts >= split else year, **holding(one, 1)})
    return found


def parse_text(plain: str, layouts: list[str]) -> dict:
    year = year_end(plain)
    holdings, totals, sectors = [], None, {}
    for layout in layouts:
        if "No. of shares" in layout:
            holdings += holdings_on(layout, year)
    # Columns are two or more spaces apart; one space is a thousands separator
    for match in re.finditer(rf"^\s*({NUM})\s{{2,}}({NUM})\s*$", plain, re.M):
        if len(match.group(1)) > 10:  # the first pair of rand totals over R1 billion is the holdings total
            totals = {year: number(match.group(1)), year - 1: number(match.group(2))}
            break
    for sector in SECTORS:
        found = re.search(rf"^{sector}\s+({NUM}|-)\s{{2,}}({NUM}|-)\s*$", plain, re.M)
        alone = re.search(rf"^{sector}\s+({NUM})\s*$", plain, re.M)
        if found:
            sectors[sector] = {year: 0.0 if found.group(1) == "-" else number(found.group(1)),
                               year - 1: 0.0 if found.group(2) == "-" else number(found.group(2))}
        elif alone:  # a retired industry printed only in the prior-year column
            sectors[sector] = {year: 0.0, year - 1: number(alone.group(1))}
    if not holdings or not totals:
        raise UnparsedStatement(f"holdings or totals not found in the {year} statement")
    return {"year": year, "holdings": holdings, "totals": totals, "sectors": sectors}


def parse(pdf: bytes) -> dict:
    return parse_text(*extract(pdf))
