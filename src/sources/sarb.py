"""SARB time series from the Reserve Bank's public web API, returned as the raw JSON bytes received."""

import json

import requests

try:
    import truststore  # uses the operating system's certificate store; verification stays on

    truststore.inject_into_ssl()
except ImportError:
    pass


def fetch(url_template: str, series: str, start: str, end: str) -> bytes:
    response = requests.get(url_template.format(series=series, start=start, end=end),
                            headers={"User-Agent": "fund-performance-attribution"}, timeout=60)
    response.raise_for_status()
    json.loads(response.content)  # refuse to land anything that is not JSON
    return response.content


def observations(payload: bytes) -> list[dict]:
    return [{"period": row["Period"][:10], "value": row["Value"], "description": row.get("Timeseries")}
            for row in json.loads(payload)]
