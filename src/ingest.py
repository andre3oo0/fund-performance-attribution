"""Collect today's files from Yahoo and SARB and land them unchanged in the private data repository."""

import argparse
import sys
from datetime import datetime

from src import config, landing
from src.sources import sarb, yahoo


class IncompleteFetch(Exception):
    pass


def land_yahoo(snapshot_date: str, refetch: bool, now: datetime) -> dict:
    settings = config.sources()["yahoo"]
    symbols = [i["vendor_symbol"] for i in config.instruments()]
    prices, statuses = yahoo.fetch(symbols, str(settings["start"]))
    returned = sum(s.status == "ok" for s in statuses)
    if returned / len(symbols) < settings["min_coverage"]:
        failed = ", ".join(s.vendor_symbol for s in statuses if s.status != "ok")
        raise IncompleteFetch(f"Yahoo returned {returned}/{len(symbols)} symbols; nothing landed. Failed: {failed}")
    # Only completed sessions are stored, so an intraday price is never kept as a close
    complete = prices[prices["price_date"] <= landing.session_cutoff(snapshot_date, now)]
    payload = complete.to_csv(index=False, lineterminator="\n").encode("utf-8")
    _, manifest = landing.write("yahoo", snapshot_date, "prices.csv.gz", payload, {
        "start": str(settings["start"]),
        "rows": len(complete),
        "excluded_incomplete_session_rows": len(prices) - len(complete),
        "symbols": [s.__dict__ for s in statuses],
    }, refetch=refetch, now=now)
    return manifest


def land_sarb(snapshot_date: str, refetch: bool, now: datetime) -> dict:
    settings = config.sources()["sarb"]
    series = settings["series"]
    payload = sarb.fetch(settings["url"], series, str(settings["start"]), snapshot_date)
    _, manifest = landing.write("sarb", snapshot_date, f"{series}.json.gz", payload, {
        "series": series,
        "start": str(settings["start"]),
        "rows": len(sarb.observations(payload)),
    }, refetch=refetch, now=now)
    return manifest


LANDERS = {"yahoo": land_yahoo, "sarb": land_sarb}


def main(argv=None) -> int:
    now = datetime.now(landing.SAST)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", action="append", choices=LANDERS, help="repeatable; default is every source")
    p.add_argument("--snapshot-date", default=now.date().isoformat())
    p.add_argument("--refetch", action="store_true", help="replace a snapshot already landed for this date")
    args = p.parse_args(argv)

    failed = False
    for name in args.source or list(LANDERS):
        try:
            manifest = LANDERS[name](args.snapshot_date, args.refetch, now)
            print(f"{name} {args.snapshot_date}: {manifest['rows']:,} rows landed, cut-off {manifest['session_cutoff']}")
            for s in manifest.get("symbols", []):
                if s["status"] != "ok":
                    print(f"  {s['vendor_symbol']}: {s['status']} {s['error'] or ''}")
        except landing.AlreadyLanded as exc:
            print(f"{name}: {exc}")
        except Exception as exc:  # noqa: BLE001 - one failed source must not stop the others landing
            print(f"FAILED {name}: {type(exc).__name__}: {exc}", file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
