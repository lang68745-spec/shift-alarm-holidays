#!/usr/bin/env python3
"""Find and normalize an annual holiday notice from the official gov.cn index."""

from __future__ import annotations

import argparse
import html
import json
import re
import urllib.parse
import urllib.request
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SEARCH_URL = "https://sousuo.www.gov.cn/search-gov/data"
USER_AGENT = "ShiftAlarmHolidayUpdater/1.0"
CHINESE_NUMERALS = "一二三四五六七八九十"


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        cleaned = data.strip()
        if cleaned:
            self.parts.append(cleaned)


def request_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def request_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def plain_text(value: str) -> str:
    return re.sub(r"\s+", "", html.unescape(re.sub(r"<[^>]+>", "", value)))


def find_notice(year: int) -> dict | None:
    title = f"国务院办公厅关于{year}年部分节假日安排的通知"
    query = urllib.parse.urlencode({
        "t": "zhengcelibrary",
        "q": title,
        "p": 1,
        "n": 10,
        "sort": "score",
        "sortType": 1,
        "searchfield": "title:content:summary",
    })
    payload = request_json(f"{SEARCH_URL}?{query}")
    if payload.get("code") != 200:
        raise RuntimeError(f"gov.cn search failed: {payload.get('code')} {payload.get('msg')}")
    result = payload.get("searchVO", {}).get("catMap", {}).get("gongwen", {})
    for item in result.get("listVO") or []:
        if plain_text(item.get("title", "")) == title:
            if urllib.parse.urlparse(item.get("url", "")).hostname != "www.gov.cn":
                raise RuntimeError("Matched notice is not hosted on www.gov.cn")
            return item
    return None


def html_to_text(source: str) -> str:
    parser = TextExtractor()
    parser.feed(source)
    return re.sub(r"\s+", "", " ".join(parser.parts))


def make_date(year: int, month: int, day: int) -> date:
    return date(year, month, day)


def expand_days_off(expression: str, schedule_year: int) -> list[str]:
    range_pattern = re.compile(
        r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日(?:（[^）]*）)?至"
        r"(?:(\d{4})年)?(?:(\d{1,2})月)?(\d{1,2})日"
    )
    match = range_pattern.search(expression)
    if match:
        start_year = int(match.group(1) or schedule_year)
        start_month = int(match.group(2))
        start_day = int(match.group(3))
        end_year = int(match.group(4) or start_year)
        end_month = int(match.group(5) or start_month)
        end_day = int(match.group(6))
        start = make_date(start_year, start_month, start_day)
        end = make_date(end_year, end_month, end_day)
        if end < start and match.group(4) is None:
            end = make_date(start_year + 1, end_month, end_day)
        if (end - start).days > 31:
            raise ValueError(f"Unreasonable holiday range: {expression}")
        result: list[str] = []
        current = start
        while current <= end:
            result.append(current.isoformat())
            current += timedelta(days=1)
        return result

    single = re.search(r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日", expression)
    if not single:
        raise ValueError(f"Cannot find holiday date: {expression}")
    return [
        make_date(
            int(single.group(1) or schedule_year),
            int(single.group(2)),
            int(single.group(3)),
        ).isoformat()
    ]


def extract_date_tokens(expression: str, schedule_year: int) -> list[str]:
    pattern = re.compile(r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日")
    return sorted({
        make_date(
            int(match.group(1) or schedule_year),
            int(match.group(2)),
            int(match.group(3)),
        ).isoformat()
        for match in pattern.finditer(expression)
    })


def parse_notice_text(text: str, schedule_year: int) -> list[dict]:
    compact = re.sub(r"\s+", "", text)
    start = compact.find("一、")
    if start < 0:
        raise ValueError("Cannot find the first holiday clause")
    compact = compact[start:]
    endings = [index for marker in ("节假日期间", "鼓励单位和个人") if (index := compact.find(marker)) >= 0]
    if endings:
        compact = compact[:min(endings)]

    marker_pattern = re.compile(rf"[{CHINESE_NUMERALS}]+、")
    markers = [
        match for match in marker_pattern.finditer(compact)
        if match.start() == 0 or compact[match.start() - 1] == "。"
    ]
    chunks = [
        compact[marker.start():(markers[index + 1].start() if index + 1 < len(markers) else len(compact))]
        for index, marker in enumerate(markers)
    ]
    periods: list[dict] = []
    for chunk in chunks:
        clause = re.sub(rf"^[{CHINESE_NUMERALS}]+、", "", chunk)
        if "：" not in clause or "放假" not in clause:
            continue
        name, details = clause.split("：", 1)
        holiday_expression = details.split("放假", 1)[0]
        days_off = expand_days_off(holiday_expression, schedule_year)
        adjusted: list[str] = []
        for work_match in re.finditer(r"([^。；]*?)上班", details):
            adjusted.extend(extract_date_tokens(work_match.group(1), schedule_year))
        periods.append({
            "name": name.strip(),
            "daysOff": sorted(set(days_off)),
            "adjustedWorkdays": sorted(set(adjusted)),
        })

    if len(periods) < 6:
        raise ValueError(f"Expected at least 6 holiday clauses, found {len(periods)}")
    return periods


def normalize_document(item: dict, schedule_year: int, page_text: str, revision: int) -> dict:
    periods = parse_notice_text(page_text, schedule_year)
    return {
        "schemaVersion": 1,
        "year": schedule_year,
        "version": f"{schedule_year}.{revision}",
        "publishedAt": item["pubtimeStr"].replace(".", "-"),
        "timezone": "Asia/Shanghai",
        "source": {
            "publisher": "国务院办公厅",
            "documentNumber": plain_text(item.get("pcode", "")),
            "url": item["url"],
        },
        "periods": periods,
        "daysOff": sorted({day for period in periods for day in period["daysOff"]}),
        "adjustedWorkdays": sorted({
            day for period in periods for day in period["adjustedWorkdays"]
        }),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or ROOT / "holidays" / f"{args.year}.json"

    item = find_notice(args.year)
    if item is None:
        print(f"No official {args.year} holiday notice found.")
        return 0

    existing: dict | None = None
    if output.exists():
        existing = json.loads(output.read_text(encoding="utf-8"))
    revision = 1
    if existing:
        revision = int(existing["version"].split(".", 1)[1]) + 1

    page_text = html_to_text(request_text(item["url"]))
    document = normalize_document(item, args.year, page_text, revision)
    comparable = dict(document)
    comparable.pop("version")
    if existing:
        existing_comparable = dict(existing)
        existing_comparable.pop("version", None)
        if existing_comparable == comparable:
            print(f"Official {args.year} data is unchanged.")
            return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output)
    print(f"Wrote candidate data to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
