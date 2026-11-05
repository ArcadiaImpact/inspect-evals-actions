"""Slow-test check over pytest report logs."""

import json
import subprocess
import sys
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
    assert "| Fail | 20.50s | <code>tests/a.py::fail</code> |" in summary
    assert "| Warning | 11.90s | <code>tests/a.py::warn</code> |" in summary


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


def test_main_fails_at_the_default_fail_threshold(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in ("SLOW_TEST_REPORT_THRESHOLD", "SLOW_TEST_FAIL_THRESHOLD", "GITHUB_STEP_SUMMARY"):
        monkeypatch.delenv(name, raising=False)
    report = tmp_path / "pytest-report.jsonl"
    report.write_text(_report("tests/a.py::t", 60.0) + "\n")
    assert main(["--report", str(report)]) == 1


def test_reports_dir_is_searched_recursively(thresholds: Path, tmp_path: Path) -> None:
    # download-artifact without a name puts each artifact in its own subdirectory.
    nested = tmp_path / "reports" / "pytest-report-ubuntu-py3.11"
    nested.mkdir(parents=True)
    (nested / "pytest-report.jsonl").write_text(_report("tests/a.py::fail", 30.0) + "\n")
    assert main(["--reports-dir", str(tmp_path / "reports")]) == 1


def test_repeated_report_options_are_all_read(thresholds: Path, tmp_path: Path) -> None:
    first, second = tmp_path / "one.jsonl", tmp_path / "two.jsonl"
    first.write_text(_report("tests/a.py::warn", 11.0) + "\n")
    second.write_text(_report("tests/a.py::fail", 21.0) + "\n")
    warn_out = tmp_path / "warn.txt"
    assert main(["--report", str(first), "--report", str(second), "--warn-output", str(warn_out)]) == 1
    assert warn_out.read_text() == "11.00s\ttests/a.py::warn\n"


def test_missing_report_is_an_error(
    thresholds: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The old inline heavy check crashed here, which kept Slack and triage firing
    # when the test step never wrote a report.
    fail_out = tmp_path / "fail.txt"
    code = main(["--report", str(tmp_path / "missing.jsonl"), "--fail-output", str(fail_out)])
    assert code == 2
    assert "::error title=Slow test check::No pytest report to check" in capsys.readouterr().out
    assert "No pytest report to check" in thresholds.read_text()
    assert not fail_out.exists()


def test_empty_reports_dir_is_an_error(thresholds: Path, tmp_path: Path) -> None:
    (tmp_path / "reports").mkdir()
    assert main(["--reports-dir", str(tmp_path / "reports")]) == 2


def test_null_keywords_and_non_object_lines_are_tolerated() -> None:
    line = json.dumps(
        {
            "$report_type": "TestReport",
            "nodeid": "tests/a.py::t",
            "when": "call",
            "outcome": "passed",
            "duration": 12.0,
            "keywords": None,
        }
    )
    slow_tests = _collect(["[]", "null", "3", line])
    assert slow_tests.warnings == [("tests/a.py::t", 12.0)]


def test_node_ids_with_markdown_and_command_characters_are_escaped() -> None:
    nodeid = 'tests/a.py::t[```json\n{"a": "b|c"}\n``` 100%]'
    slow_tests = _collect([_report(nodeid, 25.0)])

    [annotation] = annotations(slow_tests)
    assert "\n" not in annotation
    assert "%0A" in annotation
    assert "100%25" in annotation

    [row] = [line for line in step_summary(slow_tests, "t").splitlines() if line.startswith("| Fail")]
    assert row.count("|") == 4  # The pipe inside the node ID does not add a cell.
    assert "```" in row
    assert "&#124;" in row
    assert "<code>" in row


def test_script_runs_by_path(tmp_path: Path) -> None:
    # The workflows run the file directly rather than importing it.
    report = tmp_path / "pytest-report.jsonl"
    report.write_text(_report("tests/a.py::fail", 30.0) + "\n")
    script = Path(__file__).resolve().parents[1] / "scripts" / "build" / "check_slow_tests.py"
    result = subprocess.run(
        [sys.executable, str(script), "--report", str(report)],
        capture_output=True,
        text=True,
        env={"SLOW_TEST_REPORT_THRESHOLD": "10", "SLOW_TEST_FAIL_THRESHOLD": "20"},
        check=False,
    )
    assert result.returncode == 1, result.stderr
    assert "tests/a.py::fail [FAIL]" in result.stdout
