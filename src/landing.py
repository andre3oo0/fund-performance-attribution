"""Land vendor files exactly as received: gzipped, fingerprinted, never overwritten without an explicit refetch."""

import gzip
import hashlib
import json
import uuid
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

from src import config

SAST = timezone(timedelta(hours=2))  # no daylight saving, so a fixed offset is exact
SESSION_FINAL = time(17, 30)  # JSE closes at 17:00; allow for the closing auction and vendor publication
MANIFEST_FILE = "manifest.json"


class AlreadyLanded(Exception):
    pass


class TamperedLanding(RuntimeError):
    pass


def landing_dir(source: str, snapshot_date: str) -> Path:
    return config.LANDING_DIR / source / snapshot_date


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def session_cutoff(snapshot_date: str, fetched: datetime) -> str:
    snap = datetime.fromisoformat(snapshot_date).date()
    local = fetched.astimezone(SAST)
    final = local.date() > snap or (local.date() == snap and local.time() >= SESSION_FINAL)
    return snapshot_date if final else (snap - timedelta(days=1)).isoformat()


def write(source: str, snapshot_date: str, filename: str, payload: bytes, details: dict,
          refetch: bool = False, now: datetime | None = None) -> tuple[Path, dict]:
    now = now or datetime.now(SAST)
    out = landing_dir(source, snapshot_date)
    data_path, manifest_path = out / filename, out / MANIFEST_FILE
    if manifest_path.exists() and not refetch:
        raise AlreadyLanded(f"{source} {snapshot_date} is already landed; pass --refetch to replace it")
    out.mkdir(parents=True, exist_ok=True)
    # mtime=0 keeps the gzip header timestamp-free, so identical content gives an identical hash
    data_path.write_bytes(gzip.compress(payload, mtime=0))
    manifest = {
        "run_id": str(uuid.uuid4()),
        "source": source,
        "snapshot_date": snapshot_date,
        "fetched_at": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "session_cutoff": session_cutoff(snapshot_date, now),
        "file": filename,
        "sha256": sha256(data_path),
        **details,
    }
    # LF on every OS, so a manifest is byte-identical wherever it was written
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    return data_path, manifest


def read(manifest_path: Path) -> tuple[bytes, dict]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    data_path = manifest_path.parent / manifest["file"]
    if sha256(data_path) != manifest["sha256"]:
        raise TamperedLanding(f"{data_path} does not match its manifest hash; the landed file was changed")
    return gzip.decompress(data_path.read_bytes()), manifest


def manifests() -> list[Path]:
    return sorted(config.LANDING_DIR.glob(f"*/*/{MANIFEST_FILE}"))
