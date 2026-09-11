#!/usr/bin/env python3
"""Validate published holiday files and their manifest using stdlib only."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VERSION_RE = re.compile(r"^(\d{4})\.([1-9]\d*)$")


class ValidationError(ValueError):
    pass


def fail(message: str) -> None:
    raise ValidationError(message)


def parse_date(value: object, field: str) -> date:
    if not isinstance(value, str) or not DATE_RE.fullmatch(value):
        fail(f"{field}: expected yyyy-MM-dd")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        fail(f"{field}: invalid date {value}: {exc}")


def validate_string_list(values: object, field: str) -> list[str]:
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        fail(f"{field}: expected a string array")
    if len(values) != len(set(values)):
        fail(f"{field}: duplicate dates")
    if values != sorted(values):
        fail(f"{field}: dates must be sorted")
    return values


def validate_document(data: object, expected_year: int | None = None) -> None:
    if not isinstance(data, dict):
        fail("document: expected an object")

    required = {
        "schemaVersion", "year", "version", "publishedAt", "timezone",
        "source", "periods", "daysOff", "adjustedWorkdays",
    }
    extra = set(data) - required
    missing = required - set(data)
    if missing or extra:
        fail(f"document keys: missing={sorted(missing)} extra={sorted(extra)}")

    if data["schemaVersion"] != 1:
        fail("schemaVersion: only version 1 is supported")
    year = data["year"]
    if not isinstance(year, int) or not 2000 <= year <= 2100:
        fail("year: expected an integer from 2000 through 2100")
    if expected_year is not None and year != expected_year:
        fail(f"year: expected {expected_year}, got {year}")

    version = data["version"]
    match = VERSION_RE.fullmatch(version) if isinstance(version, str) else None
    if not match or int(match.group(1)) != year:
        fail("version: expected <year>.<positive revision>")
    parse_date(data["publishedAt"], "publishedAt")
    if data["timezone"] != "Asia/Shanghai":
        fail("timezone: must be Asia/Shanghai")

    source = data["source"]
    if not isinstance(source, dict) or set(source) != {"publisher", "documentNumber", "url"}:
        fail("source: invalid keys")
    if source["publisher"] != "国务院办公厅":
        fail("source.publisher: must be 国务院办公厅")
    if not isinstance(source["documentNumber"], str) or not source["documentNumber"].strip():
        fail("source.documentNumber: required")
    parsed_url = urlparse(source["url"] if isinstance(source["url"], str) else "")
    if parsed_url.scheme != "https" or parsed_url.hostname != "www.gov.cn":
        fail("source.url: must use https://www.gov.cn/")

    periods = data["periods"]
    if not isinstance(periods, list) or not periods:
        fail("periods: expected a non-empty array")

    period_names: set[str] = set()
    union_days_off: set[str] = set()
    union_workdays: set[str] = set()
    for index, period in enumerate(periods):
        prefix = f"periods[{index}]"
        if not isinstance(period, dict) or set(period) != {"name", "daysOff", "adjustedWorkdays"}:
            fail(f"{prefix}: invalid keys")
        name = period["name"]
        if not isinstance(name, str) or not name.strip() or name in period_names:
            fail(f"{prefix}.name: missing or duplicate")
        period_names.add(name)
        days_off = validate_string_list(period["daysOff"], f"{prefix}.daysOff")
        workdays = validate_string_list(period["adjustedWorkdays"], f"{prefix}.adjustedWorkdays")
        if not days_off:
            fail(f"{prefix}.daysOff: cannot be empty")
        if set(days_off) & set(workdays):
            fail(f"{prefix}: a date cannot be both off and adjusted work")
        union_days_off.update(days_off)
        union_workdays.update(workdays)

    days_off = validate_string_list(data["daysOff"], "daysOff")
    workdays = validate_string_list(data["adjustedWorkdays"], "adjustedWorkdays")
    if set(days_off) != union_days_off:
        fail("daysOff: must equal the union of period days")
    if set(workdays) != union_workdays:
        fail("adjustedWorkdays: must equal the union of period workdays")
    if set(days_off) & set(workdays):
        fail("document: a date cannot be both off and adjusted work")

    for field, values in (("daysOff", days_off), ("adjustedWorkdays", workdays)):
        for index, value in enumerate(values):
            parsed = parse_date(value, f"{field}[{index}]")
            if parsed.year not in {year - 1, year}:
                fail(f"{field}[{index}]: date is outside the schedule year")


def validate_repository(root: Path = ROOT) -> None:
    files = sorted((root / "holidays").glob("*.json"))
    if not files:
        fail("holidays: no annual data files found")

    documents: dict[int, tuple[Path, dict]] = {}
    for path in files:
        try:
            year = int(path.stem)
        except ValueError:
            fail(f"{path}: filename must be a four-digit year")
        data = json.loads(path.read_text(encoding="utf-8"))
        validate_document(data, year)
        documents[year] = (path, data)

    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        fail("manifest.json: missing; run scripts/build_manifest.py")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if set(manifest) != {"schemaVersion", "updatedAt", "years"}:
        fail("manifest.json: invalid keys")
    if manifest["schemaVersion"] != 1:
        fail("manifest.schemaVersion: only version 1 is supported")
    parse_date(manifest["updatedAt"], "manifest.updatedAt")
    years = manifest["years"]
    if not isinstance(years, dict) or set(years) != {str(year) for year in documents}:
        fail("manifest.years: must match annual data files")

    for year, (path, data) in documents.items():
        entry = years[str(year)]
        expected_path = f"holidays/{year}.json"
        expected_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        expected = {
            "version": data["version"],
            "path": expected_path,
            "sha256": expected_sha,
            "publishedAt": data["publishedAt"],
        }
        if entry != expected:
            fail(f"manifest.years.{year}: stale or invalid; rebuild the manifest")


def main() -> int:
    try:
        validate_repository()
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print("Holiday data validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

