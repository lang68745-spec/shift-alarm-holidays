#!/usr/bin/env python3
"""Build the deterministic App update manifest from reviewed annual files."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    years: dict[str, dict[str, str]] = {}
    published_dates: list[str] = []
    for path in sorted((ROOT / "holidays").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        year = str(data["year"])
        published_dates.append(data["publishedAt"])
        years[year] = {
            "version": data["version"],
            "path": f"holidays/{path.name}",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "publishedAt": data["publishedAt"],
        }

    if not years:
        raise SystemExit("No annual holiday files found.")
    manifest = {
        "schemaVersion": 1,
        "updatedAt": max(published_dates),
        "years": years,
    }
    (ROOT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

