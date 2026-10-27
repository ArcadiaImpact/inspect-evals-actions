"""Split heavy-test failures into Hugging Face access denials and other failures.

Usage: python3 scripts/heavy/classify_failures.py pytest-report.jsonl

Reads a pytest-reportlog file and prints a JSON object to stdout. Uses only the
standard library so that workflows can run it with the runner's python3.
"""

import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

ACCESS_DENIED_KEY = "hf_access_denied"
SUMMARY_LIMIT = 500


def _error_summary(report: dict[str, Any]) -> str:
    longrepr = report.get("longrepr") or ""
    if isinstance(longrepr, dict):
        longrepr = longrepr.get("reprcrash", {}).get("message", "")
    return str(longrepr)[:SUMMARY_LIMIT]


def _access_denied_repo_id(report: dict[str, Any]) -> str | None:
    for prop in report.get("user_properties") or []:
        if isinstance(prop, (list, tuple)) and len(prop) == 2 and prop[0] == ACCESS_DENIED_KEY:
            return str(prop[1] or "")
    return None


def classify(lines: Iterable[str]) -> dict[str, list[dict[str, str]]]:
    access_denied: list[dict[str, str]] = []
    other_failures: list[dict[str, str]] = []
    for line in lines:
        try:
            report = json.loads(line)
        except ValueError:
            continue
        if not isinstance(report, dict):
            continue
        if (
            report.get("$report_type") != "TestReport"
            or report.get("when") != "call"
            or report.get("outcome") != "failed"
        ):
            continue
        node_id = str(report.get("nodeid", ""))
        repo_id = _access_denied_repo_id(report)
        if repo_id is not None:
            access_denied.append({"node_id": node_id, "repo_id": repo_id})
        else:
            other_failures.append(
                {"node_id": node_id, "error_summary": _error_summary(report)}
            )
    return {"access_denied": access_denied, "other_failures": other_failures}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: classify_failures.py <pytest-report.jsonl>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    if path.is_file():
        with path.open(encoding="utf-8") as f:
            result = classify(f)
    else:
        result = classify([])
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
