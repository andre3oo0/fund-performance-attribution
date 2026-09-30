"""Paths and config loading, resolved from the repository root so tools run the same from anywhere."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
SQL_DIR = ROOT / "sql"
DATA_DIR = ROOT / "data"
# data/landing is a clone of the private jse-price-data repository; this project keeps its own folder there
LANDING_DIR = DATA_DIR / "landing" / "fund-performance-attribution"
DB_PATH = DATA_DIR / "warehouse.db"


def load_yaml(name: str) -> dict:
    with open(CONFIG_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


def sources() -> dict:
    return load_yaml("sources.yaml")


def instruments() -> list[dict]:
    listed = list(sources()["yahoo"]["instruments"])
    if (CONFIG_DIR / "securities.yaml").exists():
        listed += load_yaml("securities.yaml").get("securities") or []
    return listed
