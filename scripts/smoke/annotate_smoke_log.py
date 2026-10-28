"""Turn a smoke test log into GitHub annotations and a job summary.

Usage: python3 scripts/smoke/annotate_smoke_log.py <smoke_output.log> <title>

Prints one ::error or ::warning workflow command per problem, so the run page
names each failing task, and appends a markdown summary to $GITHUB_STEP_SUMMARY
when it is set. It always exits 0: summarise_smoke_test_log.sh decides whether
the run fails.

Uses only the standard library, because workflows run it with the runner's
Python rather than the project environment.
"""

from __future__ import annotations

import ast
import os
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field

TASK = r"task \d+ of \d+ \((?P<task>[^)]+)\)"
TESTING = re.compile(r"Testing eval .*" + TASK)
SUCCEEDED = re.compile(r"Succeeded: .*" + TASK)
SKIPPED = re.compile(r"Skipping eval .*" + TASK)
TIMED_OUT = re.compile(r"Timed out: .*" + TASK)
UNEXPECTED = re.compile(r"Error on .*?" + TASK + r" .*is not considered acceptable")
ACCESS_DENIED = re.compile(
    r"Hugging Face access denied on .*?" + TASK + r": dataset (?P<repo>\S+)"
    r"(?: \(accept the terms at (?P<url>\S+)\))?"
)
STALE = re.compile(r"Task task_name='(?P<task>[^']+)' is in SKIPPABLE_TASKS, but should be removed")
ERROR_OUTPUT = "error.output="
# A Python exception line, e.g. "ValueError: ..." or "tenacity.RetryError: ...".
EXCEPTION_LINE = re.compile(r"^[A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt)\b")
NO_ERROR_DETAIL = "See the Smoke test job log for the error."


@dataclass
class SmokeResult:
    total: int = 0
    succeeded: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    timeouts: list[str] = field(default_factory=list)
    unexpected: list[tuple[str, str]] = field(default_factory=list)
    access_denied: list[tuple[str, str, str | None]] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)


def _last_error_line(line: str) -> str:
    """Return the last exception line, else the last line, of the eval output after error.output=."""
    _, sep, literal = line.partition(ERROR_OUTPUT)
    if not sep:
        return NO_ERROR_DETAIL
    try:
        output = ast.literal_eval(literal.strip())
    except (ValueError, SyntaxError):
        return NO_ERROR_DETAIL
    if not isinstance(output, str):
        return NO_ERROR_DETAIL
    lines = [text.strip() for text in output.splitlines() if text.strip()]
    exception_lines = [text for text in lines if EXCEPTION_LINE.match(text)]
    if exception_lines:
        return exception_lines[-1]
    return lines[-1] if lines else NO_ERROR_DETAIL


def parse_log(lines: Iterable[str]) -> SmokeResult:
    result = SmokeResult()
    for raw in lines:
        line = raw.rstrip("\r\n")
        if match := TESTING.search(line):
            result.total += 1
        elif match := SUCCEEDED.search(line):
            result.succeeded.append(match["task"])
        elif match := SKIPPED.search(line):
            result.skipped.append(match["task"])
        elif match := TIMED_OUT.search(line):
            result.timeouts.append(match["task"])
        elif match := ACCESS_DENIED.search(line):
            result.access_denied.append((match["task"], match["repo"], match["url"]))
        elif match := UNEXPECTED.search(line):
            result.unexpected.append((match["task"], _last_error_line(line)))
        elif match := STALE.search(line):
            result.stale.append(match["task"])
    return result


def _escape(text: str) -> str:
    """Escape a workflow command message, which ends at the first line break."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(text: str) -> str:
    return _escape(text).replace(":", "%3A").replace(",", "%2C")


def _command(level: str, title: str, message: str) -> str:
    return f"::{level} title={_escape_property(title)}::{_escape(message)}"


def annotations(result: SmokeResult) -> list[str]:
    lines = [
        _command("error", f"Smoke test failed ({task})", message)
        for task, message in result.unexpected
    ]
    for task, repo, url in result.access_denied:
        message = (
            f"Accept the terms for {repo} at {url}"
            if url
            else "The dataset could not be identified; see the Smoke test job log."
        )
        lines.append(_command("error", f"Hugging Face access denied ({task})", message))
    lines += [
        _command(
            "warning",
            f"Smoke test timed out ({task})",
            "The task did not finish within the eval timeout.",
        )
        for task in result.timeouts
    ]
    lines += [
        _command(
            "warning",
            f"Out-of-date skip ({task})",
            "The task passed, so remove it from SKIPPABLE_TASKS in tools/run_evals.py.",
        )
        for task in result.stale
    ]
    return lines


def step_summary(result: SmokeResult, title: str) -> str:
    rows = [
        ("Total evals", result.total),
        ("Successes", len(result.succeeded)),
        ("Expected skips", len(result.skipped)),
        ("Timeouts", len(result.timeouts)),
        ("Unexpected errors", len(result.unexpected)),
        ("Hugging Face access denied", len(result.access_denied)),
        ("Out-of-date skips", len(result.stale)),
    ]
    parts = [f"## {title}", "", "| Result | Count |", "| --- | --- |"]
    parts += [f"| {name} | {count} |" for name, count in rows]
    sections = [
        ("Unexpected errors", [f"- `{task}`: {message}" for task, message in result.unexpected]),
        (
            "Hugging Face access denied (accept the terms; no code fix)",
            [
                f"- `{task}`: [{repo}]({url})" if url else f"- `{task}`: dataset unknown"
                for task, repo, url in result.access_denied
            ],
        ),
        ("Timeouts", [f"- `{task}`" for task in result.timeouts]),
        ("Out-of-date skips (remove from SKIPPABLE_TASKS)", [f"- `{task}`" for task in result.stale]),
    ]
    listed = [(heading, items) for heading, items in sections if items]
    if not listed:
        parts += ["", "No unexpected errors, access denials, timeouts or out-of-date skips."]
    for heading, items in listed:
        parts += ["", f"### {heading}", "", *items]
    return "\n".join(parts) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(f"usage: {argv[0]} <smoke_output.log> <title>", file=sys.stderr)
        return 2
    log_path, title = argv[1], argv[2]
    try:
        with open(log_path, encoding="utf-8", errors="replace") as log:
            result = parse_log(log)
    except FileNotFoundError:
        print(_command("warning", "Smoke test log missing", f"{log_path} was not found."))
        return 0
    for line in annotations(result):
        print(line)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as summary:
            summary.write(step_summary(result, title))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
