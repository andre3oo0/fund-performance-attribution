"""Daily bars and dividends from Yahoo Finance, returned unconverted: prices in the unit Yahoo reports."""

import logging
import time
from dataclasses import dataclass

import pandas as pd
import yfinance as yf

# Outcomes are recorded in the manifest, so yfinance's own retry logging is noise
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

COLUMNS = ["vendor_symbol", "price_date", "open", "high", "low", "close", "adj_close", "volume",
           "dividends", "splits", "reported_unit"]
_RENAME = {"Open": "open", "High": "high", "Low": "low", "Close": "close", "Adj Close": "adj_close",
           "Volume": "volume", "Dividends": "dividends", "Stock Splits": "splits"}


@dataclass
class SymbolStatus:
    vendor_symbol: str
    status: str
    row_count: int
    reported_unit: str | None = None
    error: str | None = None


def fetch_one(symbol: str, start: str, attempts: int = 3) -> tuple[pd.DataFrame, SymbolStatus]:
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start, auto_adjust=False, actions=True)
            if not hist.empty:
                unit = (ticker.history_metadata or {}).get("currency")
                return to_frame(symbol, hist, unit), SymbolStatus(symbol, "ok", len(hist), unit)
            last_error = None  # usually a dead symbol, but flaky networks return empty too
        except Exception as exc:  # noqa: BLE001 - one bad symbol must not sink the run
            last_error = f"{type(exc).__name__}: {exc}"[:500]
        if attempt < attempts:
            time.sleep(2 ** attempt)
    return pd.DataFrame(columns=COLUMNS), SymbolStatus(symbol, "error" if last_error else "empty", 0, error=last_error)


def to_frame(symbol: str, hist: pd.DataFrame, unit: str | None) -> pd.DataFrame:
    df = hist.rename(columns=_RENAME).reset_index()
    # Bars are stamped at Johannesburg midnight; converting to UTC first would shift every date back a day
    df["price_date"] = df["Date"].dt.strftime("%Y-%m-%d")
    df["vendor_symbol"] = symbol
    df["reported_unit"] = unit
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df[COLUMNS]


def fetch(symbols: list[str], start: str) -> tuple[pd.DataFrame, list[SymbolStatus]]:
    results = [fetch_one(s, start) for s in symbols]
    frames = [df for df, _ in results if not df.empty]
    prices = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)
    return prices, [status for _, status in results]
