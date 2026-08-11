from __future__ import annotations

import dataclasses
import datetime as dt
import re
import sys
from typing import Any, Callable

import requests


USER_AGENT = "cns-mcdb-update/1.0 (mailto:huic@sc.edu; https://github.com/huichenlab/CNS-MCDB-Update)"


@dataclasses.dataclass(frozen=True)
class IssueCandidate:
    journal: str
    issn: str
    volume: str
    issue: str
    issue_date: str
    canonical_issue_url: str
    metadata_source: str

    @property
    def key(self) -> str:
        return f"{self.volume}:{self.issue}"


JOURNALS: dict[str, dict[str, str]] = {
    "Science": {
        "issn": "0036-8075",
        "current_url": "https://www.science.org/toc/science/current",
    },
    "Nature": {
        "issn": "0028-0836",
        "current_url": "https://www.nature.com/nature/current-issue",
    },
    "Cell": {
        "issn": "0092-8674",
        "current_url": "https://www.cell.com/cell/current",
    },
}


def _parts_date(item: dict[str, Any]) -> dt.date | None:
    for field in ("published-print", "issued", "published", "published-online"):
        parts = (item.get(field) or {}).get("date-parts") or []
        if not parts or not parts[0]:
            continue
        values = list(parts[0]) + [1, 1]
        try:
            return dt.date(int(values[0]), int(values[1]), int(values[2]))
        except (TypeError, ValueError):
            continue
    return None


def _natural_number(value: str) -> tuple[int, str]:
    match = re.search(r"\d+", value or "")
    return (int(match.group()) if match else -1, value or "")


def canonical_issue_url(journal: str, volume: str, issue: str, issue_date: str = "") -> str:
    if journal == "Science":
        return f"https://www.science.org/toc/science/{volume}/{issue}"
    if journal == "Nature":
        return f"https://www.nature.com/nature/volumes/{volume}/issues/{issue}"
    if journal == "Cell":
        try:
            year = int((issue_date or str(dt.date.today().year))[:4]) % 100
            issue_number = int(re.search(r"\d+", issue).group())
            return f"https://www.cell.com/cell/issue?pii=S0092-8674({year:02d})X{issue_number:04d}-X"
        except (AttributeError, TypeError, ValueError):
            return JOURNALS[journal]["current_url"]
    raise KeyError(journal)


def _fetch_json(url: str, params: dict[str, str | int]) -> dict[str, Any]:
    response = requests.get(
        url,
        params=params,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=45,
    )
    response.raise_for_status()
    return response.json()


def _candidate_from_items(journal: str, items: list[dict[str, Any]], today: dt.date) -> IssueCandidate:
    grouped: dict[tuple[str, str], list[dt.date]] = {}
    for item in items:
        volume = str(item.get("volume") or "").strip()
        issue = str(item.get("issue") or "").strip()
        published = _parts_date(item)
        if not volume or not issue or not published or published > today:
            continue
        grouped.setdefault((volume, issue), []).append(published)
    if not grouped:
        raise RuntimeError(f"Crossref returned no recent issue metadata for {journal}")

    def score(entry: tuple[tuple[str, str], list[dt.date]]) -> tuple[dt.date, tuple[int, str], tuple[int, str]]:
        (volume, issue), dates = entry
        return max(dates), _natural_number(volume), _natural_number(issue)

    (volume, issue), dates = max(grouped.items(), key=score)
    issue_date = max(dates).isoformat()
    config = JOURNALS[journal]
    return IssueCandidate(
        journal=journal,
        issn=config["issn"],
        volume=volume,
        issue=issue,
        issue_date=issue_date,
        canonical_issue_url=canonical_issue_url(journal, volume, issue, issue_date),
        metadata_source=f"https://api.crossref.org/journals/{config['issn']}/works",
    )


def detect_latest_issue(
    journal: str,
    *,
    today: dt.date | None = None,
    fetch_json: Callable[[str, dict[str, str | int]], dict[str, Any]] = _fetch_json,
) -> IssueCandidate:
    """Detect a candidate from publisher-deposited Crossref metadata.

    The report stage separately probes the canonical publisher issue URL and
    records whether the runner could retrieve it. Crossref remains a detector,
    not a claim of full-text or figure review.
    """

    today = today or dt.date.today()
    start = today - dt.timedelta(days=120)
    config = JOURNALS[journal]
    payload = fetch_json(
        f"https://api.crossref.org/journals/{config['issn']}/works",
        {
            "filter": f"type:journal-article,from-pub-date:{start.isoformat()},until-pub-date:{today.isoformat()}",
            "rows": 500,
            "sort": "published",
            "order": "desc",
        },
    )
    return _candidate_from_items(journal, payload["message"]["items"], today)


def detect_all_latest_issues() -> list[IssueCandidate]:
    candidates: list[IssueCandidate] = []
    failures: list[str] = []
    for journal in JOURNALS:
        try:
            candidates.append(detect_latest_issue(journal))
        except Exception as exc:
            failures.append(f"{journal}: {type(exc).__name__}: {exc}")
    for failure in failures:
        print(f"::warning::Issue detection failed for {failure}", file=sys.stderr)
    if not candidates:
        raise RuntimeError("Issue detection failed for Science, Nature, and Cell")
    return candidates


def is_new_issue(candidate: IssueCandidate, state: dict[str, Any]) -> bool:
    previous = (state.get("issues") or {}).get(candidate.journal) or {}
    previous_key = str(previous.get("release_key") or "")
    if previous_key:
        return previous_key != candidate.key
    return (
        str(previous.get("volume") or "") != candidate.volume
        or str(previous.get("issue") or "") != candidate.issue
    )
