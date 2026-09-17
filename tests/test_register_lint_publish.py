"""Validate the artifact boundary and the installed linter integration."""

import json
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from scripts.register_lint.collect import (
    CloneError,
    clone_at_commit,
    derive_layouts,
    lint_layouts,
)
from scripts.register_lint.publish import publish, validate_document
from scripts.register_lint.report import POLICY, REGISTRY_URL, EntryResult, summarise

SHA = "a" * 40


@pytest.fixture
def artifact(tmp_path):
    lint = {
        "evaluations": [
            {
                "name": "alpha",
                "results": [
                    {
                        "check": "readme",
                        "category": "file_structure",
                        "status": "pass",
                        "message": "Found README",
                    },
                    {
                        "check": "e2e_test",
                        "category": "tests",
                        "status": "fail",
                        "message": "Missing test",
                    },
                ],
            }
        ]
    }
    result = EntryResult(
        id="alpha",
        repository_url="https://github.com/owner/repo",
        commit=SHA,
        task_paths=["src/alpha/task.py"],
        status="linted",
        checked_at="2026-09-17T00:00:00+00:00",
        lint_version="0.1.1",
        lint=lint,
        score=summarise(lint),
    )
    doc = {
        "schema_version": 1,
        "registry": {"repository_url": REGISTRY_URL, "commit": SHA},
        "runner_commit": SHA,
        "lint": {"version": "0.1.1", "preset": "register", "policy": POLICY},
        "generated_at": "2026-09-17T00:00:00+00:00",
        "entries": [asdict(result)],
    }
    directory = tmp_path / "artifact"
    directory.mkdir()
    (directory / "results.json").write_text(json.dumps(doc))
    return directory, doc


def test_publication_generates_only_known_paths(artifact, tmp_path):
    directory, doc = artifact
    output = tmp_path / "public"
    publish(directory, output, "https://example.com/results")
    assert {
        p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()
    } == {
        "summary.json",
        "README.md",
        "results/alpha.json",
        "badges/alpha/lint.json",
        "badges/alpha/file_structure.json",
        "badges/alpha/code_quality.json",
        "badges/alpha/tests.json",
        "badges/alpha/best_practices.json",
    }
    summary = json.loads((output / "summary.json").read_text())
    assert summary["registry"] == doc["registry"]
    assert summary["lint"] == doc["lint"]
    assert summary["entries"][0]["task_paths"] == ["src/alpha/task.py"]
    assert summary["entries"][0]["checked_at"] == doc["entries"][0]["checked_at"]
    assert summary["entries"][0]["score"]["passing"] == 1


@pytest.mark.parametrize(
    "filename", ["README.md", ".github/workflows/attack.yml", ".git/config"]
)
def test_extra_artifact_files_are_rejected(artifact, tmp_path, filename):
    directory, _ = artifact
    extra = directory / filename
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_text("malicious")
    with pytest.raises(ValueError, match="only results.json"):
        publish(directory, tmp_path / "public", "https://example.com/results")
    assert not (tmp_path / "public").exists()


def test_artifact_symlink_is_rejected(artifact, tmp_path):
    directory, _ = artifact
    (directory / "results.json").rename(tmp_path / "outside.json")
    (directory / "results.json").symlink_to(tmp_path / "outside.json")
    with pytest.raises(ValueError, match="Invalid artifact file"):
        publish(directory, tmp_path / "public", "https://example.com/results")


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "../../.github/workflows/attack"),
        ("id", ".git"),
        ("repository_url", "https://github.com/o/r/../../evil"),
        ("repository_url", "https://github.com@evil.example/o/r"),
        ("commit", "main"),
        ("task_paths", ["../../secret"]),
        ("checked_at", "2026-01-01"),
        ("lint_version", "9.9.9"),
        ("status", "passed"),
    ],
)
def test_invalid_result_identity_is_rejected(artifact, field, value):
    _, doc = artifact
    doc["entries"][0][field] = value
    with pytest.raises(ValueError):
        validate_document(doc)


def test_duplicate_ids_are_rejected(artifact):
    _, doc = artifact
    doc["entries"].append(doc["entries"][0])
    with pytest.raises(ValueError, match="Duplicate"):
        validate_document(doc)


def test_inconsistent_counts_are_rejected(artifact):
    _, doc = artifact
    doc["entries"][0]["score"]["passing"] = 99
    with pytest.raises(ValueError, match="counts"):
        validate_document(doc)


@pytest.mark.parametrize("category,status", [("extra", "pass"), ("tests", "unknown")])
def test_unknown_checks_are_rejected(artifact, category, status):
    _, doc = artifact
    check = doc["entries"][0]["lint"]["evaluations"][0]["results"][0]
    check.update(category=category, status=status)
    with pytest.raises(ValueError, match="check result"):
        validate_document(doc)


def test_duplicate_json_keys_are_rejected(artifact, tmp_path):
    directory, _ = artifact
    (directory / "results.json").write_text(
        '{"schema_version": 1, "schema_version": 2}'
    )
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        publish(directory, tmp_path / "public", "https://example.com/results")


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/repo",
        "ext::sh -c evil",
        "git@github.com:o/r",
        "https://evil.example/o/r",
    ],
)
def test_non_github_clone_is_rejected_before_git(tmp_path, url):
    with patch("scripts.register_lint.collect._git") as git:
        with pytest.raises(CloneError, match="HTTPS GitHub"):
            clone_at_commit(url, SHA, tmp_path / "repo")
        git.assert_not_called()


def test_git_configuration_disables_hooks_symlinks_and_other_protocols(tmp_path):
    with patch("scripts.register_lint.collect.subprocess.run") as run:
        clone_at_commit("https://github.com/o/r", SHA, tmp_path / "repo")
    commands = [call.args[0] for call in run.call_args_list]
    assert ["git", "config", "core.symlinks", "false"] in commands
    assert ["git", "config", "core.hooksPath", "/dev/null"] in commands
    assert all(
        call.kwargs["env"]["GIT_ALLOW_PROTOCOL"] == "https"
        for call in run.call_args_list
    )


def test_installed_linter_reads_source_without_importing_it(tmp_path):
    package = tmp_path / "src/alpha"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("raise RuntimeError('must not execute')\n")
    (package / "task.py").write_text("raise RuntimeError('must not execute')\n")
    doc, version = lint_layouts(
        tmp_path, derive_layouts(tmp_path, ["src/alpha/task.py"])
    )
    assert version == "0.1.1"
    assert summarise(doc)["applicable"] > 0
    assert doc["evaluations"][0]["results"]


def test_publisher_has_no_upstream_checkout_or_cross_repo_token():
    workflow = yaml.safe_load(
        (Path(__file__).parents[1] / ".github/workflows/register-lint.yml").read_text()
    )
    publisher = workflow["jobs"]["publish"]
    assert publisher["permissions"] == {"contents": "write"}
    assert "refs/heads/main" in publisher["if"]
    assert "inputs.filter == ''" in publisher["if"]
    assert "github.event_name != 'pull_request'" in publisher["if"]
    checkouts = [
        step
        for step in publisher["steps"]
        if step.get("uses", "").startswith("actions/checkout@")
    ]
    assert len(checkouts) == 1
    assert "repository" not in checkouts[0]["with"]
    assert checkouts[0]["with"]["persist-credentials"] is False
    assert "secrets." not in json.dumps(workflow)
