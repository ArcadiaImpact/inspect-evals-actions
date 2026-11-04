#!/usr/bin/env python3
"""Check pytest report logs for slow tests that are missing @pytest.mark.slow.

Tests at or above the report threshold and below the fail threshold are
warnings. Tests at or above the fail threshold fail the check. Each test gets a
::warning or ::error workflow command, and a markdown table goes to
$GITHUB_STEP_SUMMARY when it is set.
"""

import argparse
import json
import math
import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_REPORT_THRESHOLD = 10.0
DEFAULT_FAIL_THRESHOLD = 60.0


@dataclass
class SlowTests:
    report_threshold: float
    fail_threshold: float
    # nodeid -> slowest call duration seen, in seconds
    durations: dict[str, float] = field(default_factory=dict)

    def _band(self, failing: bool) -> list[tuple[str, float]]:
        return sorted(
            (
                (nodeid, dur)
                for nodeid, dur in self.durations.items()
                if (dur >= self.fail_threshold) == failing
            ),
            key=lambda item: item[1],
            reverse=True,
        )

    @property
    def failures(self) -> list[tuple[str, float]]:
        return self._band(failing=True)

    @property
    def warnings(self) -> list[tuple[str, float]]:
        return self._band(failing=False)


def collect(
    lines: Iterable[str],
    slow_tests: SlowTests,
    skip_marked_slow: bool,
    include_huggingface: bool,
) -> None:
    """Add the unmarked slow tests from one report log to slow_tests."""
    for line in lines:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("$report_type") != "TestReport":
            continue
        if obj.get("when") != "call" or obj.get("outcome") == "skipped":
            continue
        keywords = obj.get("keywords") or {}
        if skip_marked_slow and "slow" in keywords:
            continue
        if not include_huggingface and "huggingface" in keywords:
            continue
        dur = float(obj.get("duration") or 0.0)
        if dur < slow_tests.report_threshold:
            continue
        nodeid = obj.get("nodeid", "<unknown>")
        slow_tests.durations[nodeid] = max(dur, slow_tests.durations.get(nodeid, 0.0))


def _escape(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(text: str) -> str:
    return _escape(text).replace(":", "%3A").replace(",", "%2C")


def annotations(slow_tests: SlowTests) -> list[str]:
    lines = []
    for level, tests, title in (
        ("error", slow_tests.failures, "Slow test missing @pytest.mark.slow"),
        ("warning", slow_tests.warnings, "Test close to the slow-test limit"),
    ):
        for nodeid, dur in tests:
            message = (
                f"{nodeid} took {dur:.2f}s. The check fails at "
                f"{slow_tests.fail_threshold:g}s without @pytest.mark.slow({math.ceil(dur)})."
            )
            lines.append(f"::{level} title={_escape_property(title)}::{_escape(message)}")
    return lines


def step_summary(slow_tests: SlowTests, title: str) -> str:
    parts = [f"## {title}", ""]
    if not slow_tests.durations:
        parts.append(
            f"No test without @pytest.mark.slow took {slow_tests.report_threshold:g}s or longer."
        )
        return "\n".join(parts) + "\n"
    parts += [
        (
            f"Tests without @pytest.mark.slow that took {slow_tests.report_threshold:g}s "
            f"or longer. The check fails at {slow_tests.fail_threshold:g}s."
        ),
        "",
        "| Result | Duration | Test |",
        "| --- | --- | --- |",
    ]
    parts += [f"| Fail | {dur:.2f}s | `{nodeid}` |" for nodeid, dur in slow_tests.failures]
    parts += [f"| Warning | {dur:.2f}s | `{nodeid}` |" for nodeid, dur in slow_tests.warnings]
    return "\n".join(parts) + "\n"


def _write_list(path: Path | None, tests: list[tuple[str, float]]) -> None:
    if path is None:
        return
    with open(path, "w", encoding="utf-8") as out:
        out.writelines(f"{dur:.2f}s\t{nodeid}\n" for nodeid, dur in tests)


def _threshold(env_var: str, default: float) -> float:
    return float(os.environ.get(env_var) or default)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--reports-dir", type=Path, help="Directory of pytest JSONL report logs")
    source.add_argument("--report", type=Path, action="append", help="A pytest JSONL report log")
    parser.add_argument(
        "--skip-marked-slow",
        action="store_true",
        help="Ignore tests marked slow (for runs that include slow tests)",
    )
    parser.add_argument(
        "--include-huggingface",
        action="store_true",
        help="Check tests marked huggingface, which are ignored by default",
    )
    parser.add_argument("--fail-output", type=Path, help="Write failing tests here")
    parser.add_argument("--warn-output", type=Path, help="Write warning tests here")
    parser.add_argument("--title", default="Slow test check", help="Job summary heading")
    args = parser.parse_args(argv)

    slow_tests = SlowTests(
        report_threshold=_threshold("SLOW_TEST_REPORT_THRESHOLD", DEFAULT_REPORT_THRESHOLD),
        fail_threshold=_threshold("SLOW_TEST_FAIL_THRESHOLD", DEFAULT_FAIL_THRESHOLD),
    )
    reports = sorted(args.reports_dir.glob("*.jsonl")) if args.reports_dir else args.report
    for report in reports:
        if not report.exists():
            print(f"Warning: {report} not found, skipping")
            continue
        with open(report, encoding="utf-8") as f:
            collect(f, slow_tests, args.skip_marked_slow, args.include_huggingface)

    _write_list(args.fail_output, slow_tests.failures)
    _write_list(args.warn_output, slow_tests.warnings)

    if slow_tests.durations:
        print(
            f"Tests without @pytest.mark.slow that took {slow_tests.report_threshold:g}s "
            f"or longer (the check fails at {slow_tests.fail_threshold:g}s):"
        )
        for nodeid, dur in slow_tests.failures:
            print(f"{dur:6.2f}s  {nodeid} [FAIL]")
        for nodeid, dur in slow_tests.warnings:
            print(f"{dur:6.2f}s  {nodeid}")
    else:
        print(
            f"All tests under {slow_tests.report_threshold:g}s "
            "or properly marked with @pytest.mark.slow"
        )
    for line in annotations(slow_tests):
        print(line)

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as summary:
            summary.write(step_summary(slow_tests, args.title))

    return 1 if slow_tests.failures else 0


if __name__ == "__main__":
    sys.exit(main())
