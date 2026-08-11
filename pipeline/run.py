from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any

from .issues import JOURNALS, IssueCandidate, detect_all_latest_issues, detect_latest_issue, is_new_issue
from .qa import validate_pdf
from .report_pdf import render_report
from .research import research_issue


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 4, "issues": {}}
    return json.loads(path.read_text())


def output_paths(
    candidate: IssueCandidate,
    report: dict[str, Any],
    output_dir: Path,
    reports_dir: Path,
) -> tuple[Path, Path]:
    issue = report.get("issue") or {}
    date = str(issue.get("issue_date") or candidate.issue_date)
    journal = slug(candidate.journal)
    filename = (
        f"{journal}_v{slug(str(issue.get('volume') or candidate.volume))}_"
        f"i{slug(str(issue.get('issue') or candidate.issue))}_{date}"
    )
    year = date[:4]
    return output_dir / journal / year / f"{filename}.pdf", reports_dir / journal / year / f"{filename}.json"


def process_issue(
    candidate: IssueCandidate,
    retrieved_at: str,
    output_dir: Path,
    reports_dir: Path,
) -> tuple[Path, Path, dict[str, Any], dict[str, int]]:
    report = research_issue(candidate, retrieved_at)
    pdf_path, json_path = output_paths(candidate, report, output_dir, reports_dir)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    render_report(report, pdf_path)
    qa = validate_pdf(pdf_path)
    return pdf_path, json_path, report, qa


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitor Science, Nature, and Cell for MCDB research")
    parser.add_argument("--state", default="state/journal_issue_monitor_state.json")
    parser.add_argument("--output-dir", default="pdf")
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--journal", choices=JOURNALS)
    args = parser.parse_args()

    state_path = Path(args.state)
    state = load_state(state_path)
    candidates = [detect_latest_issue(args.journal)] if args.journal else detect_all_latest_issues()
    selected = candidates if args.force else [candidate for candidate in candidates if is_new_issue(candidate, state)]
    retrieved_at = dt.datetime.now(dt.timezone.utc).isoformat()
    completed: list[tuple[IssueCandidate, Path, Path, dict[str, Any], dict[str, int]]] = []
    failures: list[str] = []

    for candidate in selected:
        try:
            completed.append(
                (candidate, *process_issue(candidate, retrieved_at, Path(args.output_dir), Path(args.reports_dir)))
            )
        except Exception as exc:
            failures.append(f"{candidate.journal}: {type(exc).__name__}: {exc}")

    updated = json.loads(json.dumps(state))
    updated["version"] = 4
    updated.setdefault("issues", {})
    if completed:
        updated["last_successful_run"] = retrieved_at
    for candidate, pdf_path, json_path, report, qa in completed:
        issue = report["issue"]
        updated["issues"][candidate.journal] = {
            "release_key": candidate.key,
            "volume": str(issue.get("volume") or candidate.volume),
            "issue": str(issue.get("issue") or candidate.issue),
            "issue_date": str(issue.get("issue_date") or candidate.issue_date),
            "canonical_issue_url": str(issue.get("canonical_issue_url") or candidate.canonical_issue_url),
            "processed_at": retrieved_at,
            "pdf": pdf_path.as_posix(),
            "report": json_path.as_posix(),
            "qa": qa,
            "delivery": "committed directly to private GitHub repository",
            "generation": "deterministic; no OpenAI or model API",
        }
        print(f"Created and validated {pdf_path} ({qa['pages']} pages) and {json_path}")

    if completed or updated.get("version") != state.get("version"):
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(updated, indent=2) + "\n")

    for failure in failures:
        print(f"::warning::Processing failed for {failure}", file=sys.stderr)
    if not selected:
        print("No newly released issue detected; no PDF regenerated.")
    if failures and not completed:
        raise RuntimeError("Every newly detected release failed; see warnings above")


if __name__ == "__main__":
    main()
