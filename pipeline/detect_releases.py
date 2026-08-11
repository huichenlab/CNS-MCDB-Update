from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .issues import JOURNALS, detect_all_latest_issues, is_new_issue


def _load_state(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"version": 4, "issues": {}}
    return json.loads(path.read_text())


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect new Science, Nature, and Cell issues")
    parser.add_argument("--state", default="state/journal_issue_monitor_state.json")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    state = _load_state(Path(args.state))
    candidates = detect_all_latest_issues()
    selected = candidates if args.force else [candidate for candidate in candidates if is_new_issue(candidate, state)]
    journals = [candidate.journal for candidate in selected if candidate.journal in JOURNALS]
    output = os.getenv("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"has_changes={'true' if journals else 'false'}\n")
            handle.write("journals=" + json.dumps(journals, separators=(",", ":")) + "\n")
    print(json.dumps({"has_changes": bool(journals), "journals": journals}, indent=2))


if __name__ == "__main__":
    main()
