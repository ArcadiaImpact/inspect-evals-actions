"""Classification of heavy-test failures from pytest-report.jsonl."""

import json
import subprocess
import sys
from pathlib import Path

from scripts.heavy.classify_failures import classify

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "heavy" / "classify_failures.py"


def _report(nodeid: str, when: str = "call", outcome: str = "failed", **extra: object) -> str:
    return json.dumps(
        {
            "$report_type": "TestReport",
            "nodeid": nodeid,
            "when": when,
            "outcome": outcome,
            **extra,
        }
    )


def test_access_denied_report_is_separated() -> None:
    line = _report(
        "tests/a.py::test_a",
        user_properties=[["hf_access_denied", "org/name"]],
        longrepr="gated",
    )
    assert classify([line]) == {
        "access_denied": [{"node_id": "tests/a.py::test_a", "repo_id": "org/name"}],
        "other_failures": [],
    }


def test_plain_failure_is_other() -> None:
    dict_repr = _report(
        "tests/a.py::test_b",
        longrepr={"reprcrash": {"message": "boom"}},
        user_properties=[["other", "x"]],
    )
    long_repr = _report("tests/a.py::test_c", longrepr="x" * 600)
    result = classify([dict_repr, long_repr])
    assert result["access_denied"] == []
    assert result["other_failures"] == [
        {"node_id": "tests/a.py::test_b", "error_summary": "boom"},
        {"node_id": "tests/a.py::test_c", "error_summary": "x" * 500},
    ]


def test_passed_and_skipped_reports_ignored() -> None:
    lines = [
        _report("t::passed", outcome="passed"),
        _report("t::setup_ok", when="setup", outcome="passed"),
        _report("t::skipped", when="setup", outcome="skipped"),
        json.dumps({"$report_type": "CollectReport", "nodeid": "t", "outcome": "passed"}),
        json.dumps({"$report_type": "SomethingElse", "nodeid": "t", "outcome": "failed"}),
    ]
    assert classify(lines) == {"access_denied": [], "other_failures": []}


def test_failed_setup_and_teardown_are_other() -> None:
    lines = [
        _report("t::setup", when="setup", longrepr={"reprcrash": {"message": "fixture"}}),
        _report("t::teardown", when="teardown", longrepr="td"),
    ]
    assert classify(lines)["other_failures"] == [
        {"node_id": "t::setup", "error_summary": "fixture"},
        {"node_id": "t::teardown", "error_summary": "td"},
    ]


def test_failed_collect_report_is_other() -> None:
    line = json.dumps(
        {"$report_type": "CollectReport", "nodeid": "tests/bad.py", "outcome": "failed", "longrepr": "ImportError"}
    )
    assert classify([line]) == {
        "access_denied": [],
        "other_failures": [{"node_id": "tests/bad.py", "error_summary": "ImportError"}],
    }


def test_tagged_call_failure_still_access_denied() -> None:
    line = _report("t::g", when="call", user_properties=[["hf_access_denied", "o/n"]])
    assert classify([line]) == {
        "access_denied": [{"node_id": "t::g", "repo_id": "o/n"}],
        "other_failures": [],
    }


def test_malformed_lines_ignored() -> None:
    lines = ["", "not json", "[1, 2]", _report("t::bad", user_properties=[["hf_access_denied", ""]])]
    assert classify(lines) == {
        "access_denied": [{"node_id": "t::bad", "repo_id": ""}],
        "other_failures": [],
    }


def test_missing_file_gives_empty_lists(tmp_path: Path) -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path / "missing.jsonl")],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(proc.stdout) == {"access_denied": [], "other_failures": []}


def test_cli_reads_file(tmp_path: Path) -> None:
    path = tmp_path / "r.jsonl"
    path.write_text(_report("t::x", longrepr="bad") + "\n")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True, check=True
    )
    assert json.loads(proc.stdout)["other_failures"] == [
        {"node_id": "t::x", "error_summary": "bad"}
    ]
