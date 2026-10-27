import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="The summary script is run with bash on Linux"
)

SCRIPT = Path(__file__).parent.parent / "scripts" / "smoke" / "summarise_smoke_test_log.sh"

TERMS_URL = "https://huggingface.co/datasets/org/gated_ds"

CLEAN_LOG = """\
Testing eval 1 (alpha) task 1 of 1 (alpha_task)
Succeeded: eval 1 (alpha) task 1 of 1 (alpha_task)
Testing eval 2 (beta) task 1 of 1 (beta_task)
Succeeded: eval 2 (beta) task 1 of 1 (beta_task)
"""

DENIED_LINE = (
    "2026-10-27 02:10:00,123 - ERROR - Hugging Face access denied on "
    "eval 2 (beta) task 1 of 1 (beta_task): dataset org/gated_ds "
    f"(accept the terms at {TERMS_URL})"
)

DENIED_LOG = """\
Testing eval 1 (alpha) task 1 of 1 (alpha_task)
Succeeded: eval 1 (alpha) task 1 of 1 (alpha_task)
Testing eval 2 (beta) task 1 of 1 (beta_task)
""" + DENIED_LINE + "\n"


def run_script(tmp_path: Path, log_text: str) -> subprocess.CompletedProcess[str]:
    log = tmp_path / "smoke_output.log"
    log.write_text(log_text)
    return subprocess.run(
        ["bash", str(SCRIPT), str(log), "Smoke Test Summary (Test)"],
        capture_output=True,
        text=True,
        check=False,
    )


def test_access_denied_counted_and_fails(tmp_path: Path) -> None:
    result = run_script(tmp_path, DENIED_LOG)
    assert result.returncode == 1
    assert "Hugging Face access denied: 1" in result.stdout
    assert "beta_task" in result.stdout
    assert TERMS_URL in result.stdout


def test_access_denied_not_unexpected(tmp_path: Path) -> None:
    result = run_script(tmp_path, DENIED_LOG)
    assert "Unexpected errors: 0" in result.stdout


def test_unknown_dataset_is_listed_without_url(tmp_path: Path) -> None:
    line = (
        "Hugging Face access denied on eval 2 (beta) task 1 of 1 (beta_task): "
        "dataset unknown"
    )
    result = run_script(tmp_path, "Testing eval 2 (beta) task 1 of 1 (beta_task)\n" + line + "\n")
    assert result.returncode == 1
    assert "Hugging Face access denied: 1" in result.stdout
    assert "beta_task" in result.stdout


def test_clean_log_passes(tmp_path: Path) -> None:
    result = run_script(tmp_path, CLEAN_LOG)
    assert result.returncode == 0
    assert "Hugging Face access denied: 0" in result.stdout
    assert "Hugging Face access denied (accept" not in result.stdout
