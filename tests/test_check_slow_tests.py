"""Slow-test check over pytest report logs."""

import json
from pathlib import Path

import pytest

from scripts.build.check_slow_tests import (
    SlowTests,
    annotations,
    collect,
    main,
    step_summary,
)


def _report(
    nodeid: str,
    duration: float,
    *markers: str,
    when: str = "call",
    outcome: str = "passed",
) -> str:
    return json.dumps(
        {
            "$report_type": "TestReport",
            "nodeid": nodeid,
            "when": when,
            "outcome": outcome,
            "duration": duration,
            "keywords": {name: 1 for name in (nodeid, *markers)},
        }
    )


def _collect(lines: list[str], skip_marked_slow: bool = False, include_huggingface: bool = False) -> SlowTests:
    slow_tests = SlowTests(report_threshold=10.0, fail_threshold=20.0)
    collect(lines, slow_tests, skip_marked_slow, include_huggingface)
    return slow_tests


def test_durations_split_into_warning_and_failure_bands() -> None:
    slow_tests = _collect(
        [
            _report("tests/a.py::fast", 9.99),
            _report("tests/a.py::warn_low", 10.0),
            _report("tests/a.py::warn_high", 19.99),
            _report("tests/a.py::fail", 20.0),
        ]
    )
    assert slow_tests.warnings == [("tests/a.py::warn_high", 19.99), ("tests/a.py::warn_low", 10.0)]
    assert slow_tests.failures == [("tests/a.py::fail", 20.0)]


def test_setup_phase_and_skipped_reports_are_ignored() -> None:
    slow_tests = _collect(
        [
            _report("tests/a.py::setup", 30.0, when="setup"),
            _report("tests/a.py::skipped", 30.0, outcome="skipped"),
            "not json",
            json.dumps({"$report_type": "CollectReport", "duration": 30.0}),
        ]
    )
    assert slow_tests.durations == {}


def test_marked_slow_tests_are_only_skipped_when_asked() -> None:
    lines = [_report("tests/a.py::marked", 30.0, "slow")]
    assert _collect(lines).failures == [("tests/a.py::marked", 30.0)]
    assert _collect(lines, skip_marked_slow=True).durations == {}


def test_huggingface_tests_are_only_checked_when_asked() -> None:
    lines = [_report("tests/a.py::hf", 30.0, "huggingface")]
    assert _collect(lines).durations == {}
    assert _collect(lines, include_huggingface=True).failures == [("tests/a.py::hf", 30.0)]


def test_slowest_duration_wins_across_reports() -> None:
    slow_tests = _collect([_report("tests/a.py::t", 12.0), _report("tests/a.py::t", 25.0)])
    assert slow_tests.failures == [("tests/a.py::t", 25.0)]
    assert slow_tests.warnings == []


def test_annotations_use_error_for_failures_and_warning_for_the_band() -> None:
    slow_tests = _collect([_report("tests/a.py::warn", 11.9), _report("tests/a.py::fail", 20.5)])
    assert annotations(slow_tests) == [
        (
            "::error title=Slow test missing @pytest.mark.slow::tests/a.py::fail took 20.50s. "
            "The check fails at 20s without @pytest.mark.slow(21)."
        ),
        (
            "::warning title=Test close to the slow-test limit::tests/a.py::warn took 11.90s. "
            "The check fails at 20s without @pytest.mark.slow(12)."
        ),
    ]


def test_step_summary_lists_both_bands() -> None:
    slow_tests = _collect([_report("tests/a.py::warn", 11.9), _report("tests/a.py::fail", 20.5)])
    summary = step_summary(slow_tests, "Heavy tests")
    assert "| Fail | 20.50s | `tests/a.py::fail` |" in summary
    assert "| Warning | 11.90s | `tests/a.py::warn` |" in summary


def test_step_summary_when_nothing_is_slow() -> None:
    summary = step_summary(_collect([]), "Heavy tests")
    assert "No test without @pytest.mark.slow took 10s or longer." in summary


@pytest.fixture
def thresholds(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("SLOW_TEST_REPORT_THRESHOLD", "10")
    monkeypatch.setenv("SLOW_TEST_FAIL_THRESHOLD", "20")
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    return summary


def test_main_passes_with_only_warnings_and_writes_the_lists(thresholds: Path, tmp_path: Path) -> None:
    report = tmp_path / "pytest-report.jsonl"
    report.write_text(_report("tests/a.py::warn", 11.9) + "\n")
    fail_out, warn_out = tmp_path / "fail.txt", tmp_path / "warn.txt"

    code = main(
        ["--report", str(report), "--fail-output", str(fail_out), "--warn-output", str(warn_out)]
    )

    assert code == 0
    assert fail_out.read_text() == ""
    assert warn_out.read_text() == "11.90s\ttests/a.py::warn\n"
    assert "| Warning | 11.90s |" in thresholds.read_text()


def test_main_fails_at_the_fail_threshold(thresholds: Path, tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "one.jsonl").write_text(_report("tests/a.py::fail", 20.0) + "\n")
    fail_out = tmp_path / "fail.txt"

    assert main(["--reports-dir", str(reports), "--fail-output", str(fail_out)]) == 1
    assert fail_out.read_text() == "20.00s\ttests/a.py::fail\n"


def test_main_defaults_match_the_pr_check(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in ("SLOW_TEST_REPORT_THRESHOLD", "SLOW_TEST_FAIL_THRESHOLD", "GITHUB_STEP_SUMMARY"):
        monkeypatch.delenv(name, raising=False)
    report = tmp_path / "pytest-report.jsonl"
    report.write_text(_report("tests/a.py::t", 59.0) + "\n")
    assert main(["--report", str(report)]) == 0
