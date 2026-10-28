import subprocess
import sys
from pathlib import Path

from scripts.smoke.annotate_smoke_log import annotations, parse_log, step_summary

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "smoke" / "annotate_smoke_log.py"

OUTPUT = "Traceback (most recent call last):\n  File 'x.py', line 1\nValueError: The specified dataset is empty (has no samples)\n"

LOG = "\n".join(
    [
        "INFO:__main__:Testing eval 1 (alpha) task 1 of 1 (alpha_task)",
        "INFO:__main__:Succeeded: eval 1 (alpha) task 1 of 1 (alpha_task)",
        "INFO:__main__:Testing eval 2 (core_bench) task 1 of 1 (core_bench)",
        "WARNING:__main__:Error on eval 2 (core_bench) task 1 of 1 (core_bench) "
        "(error=CalledProcessError(1, ['uv'])) is not considered acceptable... "
        f"error.output={OUTPUT!r}",
        "INFO:__main__:Testing eval 3 (anima) task 1 of 1 (anima)",
        "WARNING:__main__:Hugging Face access denied on eval 3 (anima) task 1 of 1 (anima): "
        "dataset org/anima (accept the terms at https://huggingface.co/datasets/org/anima)",
        "INFO:__main__:Testing eval 4 (slow) task 1 of 1 (slow_task)",
        "WARNING:__main__:Timed out: eval 4 (slow) task 1 of 1 (slow_task) (Command timed out). e.output=None",
        "INFO:__main__:Testing eval 5 (mle_bench) task 1 of 1 (mle_bench)",
        "WARNING:__main__:Skipping eval 5 (mle_bench) task 1 of 1 (mle_bench)...reason: Missing required credentials... Not run",
        "INFO:__main__:Testing eval 6 (cybergym) task 1 of 1 (cybergym)",
        "WARNING:__main__:Task task_name='cybergym' is in SKIPPABLE_TASKS, but should be removed due to running successfully.",
        "INFO:__main__:Succeeded: eval 6 (cybergym) task 1 of 1 (cybergym)",
    ]
)


def test_parse_log_counts_and_details() -> None:
    result = parse_log(LOG.splitlines())
    assert result.total == 6
    assert result.succeeded == ["alpha_task", "cybergym"]
    assert result.unexpected == [
        ("core_bench", "ValueError: The specified dataset is empty (has no samples)")
    ]
    assert result.access_denied == [
        ("anima", "org/anima", "https://huggingface.co/datasets/org/anima")
    ]
    assert result.timeouts == ["slow_task"]
    assert result.skipped == ["mle_bench"]
    assert result.stale == ["cybergym"]


def test_annotations_are_one_per_problem() -> None:
    lines = annotations(parse_log(LOG.splitlines()))
    assert lines == [
        "::error title=Smoke test failed (core_bench)::ValueError: The specified dataset is empty (has no samples)",
        "::error title=Hugging Face access denied (anima)::Accept the terms for org/anima at https://huggingface.co/datasets/org/anima",
        "::warning title=Smoke test timed out (slow_task)::The task did not finish within the eval timeout.",
        "::warning title=Out-of-date skip (cybergym)::The task passed, so remove it from SKIPPABLE_TASKS in tools/run_evals.py.",
    ]


def test_annotation_messages_escape_workflow_command_characters() -> None:
    output = "boom\nValueError: 100% broken\r\n"
    log = [
        "WARNING:__main__:Error on eval 1 (x) task 1 of 1 (x_task) (error=E) is not considered acceptable... "
        f"error.output={output!r}"
    ]
    [line] = annotations(parse_log(log))
    assert line == "::error title=Smoke test failed (x_task)::ValueError: 100%25 broken"


def test_unexpected_error_without_parseable_output_has_a_fallback_message() -> None:
    log = [
        "WARNING:__main__:Error on eval 1 (x) task 1 of 1 (x_task) (error=E) is not considered acceptable... "
        "error.output=None"
    ]
    assert parse_log(log).unexpected == [("x_task", "See the Smoke test job log for the error.")]


def test_unknown_access_denied_dataset_has_no_url() -> None:
    log = [
        "WARNING:__main__:Hugging Face access denied on eval 1 (x) task 1 of 1 (x_task): dataset unknown"
    ]
    assert parse_log(log).access_denied == [("x_task", "unknown", None)]
    assert annotations(parse_log(log)) == [
        "::error title=Hugging Face access denied (x_task)::The dataset could not be identified; see the Smoke test job log."
    ]


def test_step_summary_lists_counts_and_problems() -> None:
    summary = step_summary(parse_log(LOG.splitlines()), "Smoke Test Summary (Ubuntu)")
    assert summary.startswith("## Smoke Test Summary (Ubuntu)\n")
    assert "| Total evals | 6 |" in summary
    assert "| Unexpected errors | 1 |" in summary
    assert "- `core_bench`: ValueError: The specified dataset is empty (has no samples)" in summary
    assert "- `anima`: [org/anima](https://huggingface.co/datasets/org/anima)" in summary
    assert "- `cybergym`" in summary


def test_clean_log_summary_says_no_problems() -> None:
    log = [
        "INFO:__main__:Testing eval 1 (alpha) task 1 of 1 (alpha_task)",
        "INFO:__main__:Succeeded: eval 1 (alpha) task 1 of 1 (alpha_task)",
    ]
    result = parse_log(log)
    assert annotations(result) == []
    assert "No unexpected errors, access denials, timeouts or out-of-date skips." in step_summary(
        result, "T"
    )


def test_cli_prints_annotations_and_appends_step_summary(tmp_path: Path) -> None:
    log_file = tmp_path / "smoke_output.log"
    log_file.write_text(LOG, encoding="utf-8")
    summary_file = tmp_path / "summary.md"
    summary_file.write_text("existing\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(log_file), "Smoke Test Summary (Ubuntu)"],
        capture_output=True,
        text=True,
        env={"GITHUB_STEP_SUMMARY": str(summary_file)},
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.splitlines()[0].startswith("::error title=Smoke test failed (core_bench)::")
    written = summary_file.read_text(encoding="utf-8")
    assert written.startswith("existing\n## Smoke Test Summary (Ubuntu)\n")


def test_cli_missing_log_exits_zero_with_a_warning(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path / "missing.log"), "T"],
        capture_output=True,
        text=True,
        env={},
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.startswith("::warning title=Smoke test log missing::")


def test_error_line_prefers_the_exception_over_later_output() -> None:
    output = "Traceback (most recent call last):\nValueError: The specified dataset is empty\nDownloaded 45 tarball(s).\n"
    log = [
        "WARNING:__main__:Error on eval 1 (x) task 1 of 1 (x_task) (error=E) is not considered acceptable... "
        f"error.output={output!r}"
    ]
    assert parse_log(log).unexpected == [("x_task", "ValueError: The specified dataset is empty")]


def test_error_line_falls_back_to_the_last_line_without_an_exception() -> None:
    log = [
        "WARNING:__main__:Error on eval 1 (x) task 1 of 1 (x_task) (error=E) is not considered acceptable... "
        f"error.output={'step one\nexit status 2\n'!r}"
    ]
    assert parse_log(log).unexpected == [("x_task", "exit status 2")]
