#!/usr/bin/env python3
"""Statically lint registered upstream repositories at their pinned commits.

The registry checkout is supplied by CI. No upstream code is installed, imported
or executed. The single JSON artifact is validated by a separate publisher.
Run from the actions repository with ``python -m scripts.register_lint.collect``.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .publish import validate_id, validate_repository_url
from .report import (
    COMMIT_RE,
    POLICY,
    REGISTRY_URL,
    SCHEMA_VERSION,
    EntryResult,
    _write_json,
    summarise,
)

REGISTER_DIR = Path("registry/register")


class CloneError(RuntimeError):
    pass


class LayoutError(RuntimeError):
    """A task file the linter cannot treat as an evaluation package (see ``derive_layouts``)."""


@dataclass
class RegisterEntry:
    id: str
    repository_url: str
    commit: str
    task_paths: list[str]


@dataclass
class EvalLayout:
    """Where one evaluation package sits, in inspect-evals-lint's terms."""

    eval_name: str
    source_root: str
    import_prefix: str


# ── Register ────────────────────────────────────────────────────────────────


def load_register_entries(
    register_dir: Path = REGISTER_DIR, filters: list[str] | None = None
) -> list[RegisterEntry]:
    """Every ``<register_dir>/<id>/eval.yaml``, optionally restricted to ids matching a filter glob."""
    entries: list[RegisterEntry] = []
    for yaml_path in sorted(register_dir.glob("*/eval.yaml")):
        if yaml_path.is_symlink() or yaml_path.parent.is_symlink():
            raise ValueError(f"Register entry must not be a symlink: {yaml_path}")
        eval_id = yaml_path.parent.name
        validate_id(eval_id)
        if filters and not any(fnmatch.fnmatch(eval_id, f) for f in filters):
            continue
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        source = data.get("source") or {}
        tasks = data.get("tasks") or []
        task_paths = [
            str(t["task_path"])
            for t in tasks
            if isinstance(t, dict) and t.get("task_path")
        ]
        if not source.get("repository_url") or not source.get("repository_commit"):
            raise ValueError(
                f"{yaml_path}: source.repository_url and source.repository_commit are required"
            )
        if not task_paths:
            raise ValueError(
                f"{yaml_path}: at least one task with task_path is required"
            )
        entries.append(
            RegisterEntry(
                id=eval_id,
                repository_url=str(source["repository_url"]).rstrip("/"),
                commit=str(source["repository_commit"]),
                task_paths=task_paths,
            )
        )
    return entries


# ── Clone ───────────────────────────────────────────────────────────────────


def _git(args: list[str], cwd: Path, timeout: int) -> None:
    env = {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_LFS_SKIP_SMUDGE": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_ALLOW_PROTOCOL": "https",
    }
    try:
        subprocess.run(
            ["git", *args],
            cwd=cwd,
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.CalledProcessError as e:
        raise CloneError(
            f"git {args[0]} failed: {e.stderr.strip() or e.stdout.strip()}"
        ) from e
    except subprocess.TimeoutExpired as e:
        raise CloneError(f"git {args[0]} timed out after {timeout}s") from e


def clone_at_commit(
    repository_url: str, commit: str, dest: Path, timeout: int = 180
) -> None:
    """Shallow-fetch exactly ``commit`` into ``dest``.

    Symlinks are checked out as plain files so a hostile repository cannot point
    the linter at files outside the clone, and nothing from the repository runs.
    """
    try:
        validate_repository_url(repository_url)
    except ValueError as e:
        raise CloneError(str(e)) from e
    if not COMMIT_RE.fullmatch(commit):
        raise CloneError(
            f"repository_commit is not a full 40-character SHA: {commit!r}"
        )
    dest.mkdir(parents=True, exist_ok=True)
    _git(["init", "-q"], dest, timeout)
    _git(["config", "core.symlinks", "false"], dest, timeout)
    _git(["config", "core.hooksPath", "/dev/null"], dest, timeout)
    _git(["remote", "add", "origin", repository_url], dest, timeout)
    _git(["fetch", "-q", "--depth", "1", "--no-tags", "origin", commit], dest, timeout)
    _git(["checkout", "-q", "--detach", "FETCH_HEAD"], dest, timeout)


# ── Layout ──────────────────────────────────────────────────────────────────


def derive_layouts(root: Path, task_paths: list[str]) -> list[EvalLayout]:
    """Map each task file to the package that inspect-evals-lint should treat as the evaluation.

    The rule lives in the linter (``inspect_evals_lint.task_layouts``): the
    evaluation is the directory holding the task file, its parent is the
    source root, and enclosing packages form the import prefix. A bare module
    or a missing file is a ``LayoutError`` with the linter's message, which the
    published record carries verbatim.
    """
    # Imported here so the register helpers stay usable without the linter installed.
    from inspect_evals_lint import UnsupportedLayoutError, task_layouts

    try:
        layouts = task_layouts(root, task_paths)
    except UnsupportedLayoutError as e:
        message = str(e)
        if "not found" in message:
            message = message.replace("not found", "not found at the pinned commit")
        raise LayoutError(message) from e
    return [
        EvalLayout(
            eval_name=layout.eval_name,
            source_root=layout.source_root,
            import_prefix=layout.import_prefix,
        )
        for layout in layouts
    ]


# ── Lint ────────────────────────────────────────────────────────────────────


def linter_version() -> str:
    """The version of the installed inspect-evals-lint, from the package itself.

    Both the document header and each entry record this, and the publisher
    rejects a document where they differ, so there must be exactly one source.
    """
    import inspect_evals_lint

    return inspect_evals_lint.__version__


def lint_task_paths(root: Path, task_paths: list[str]) -> tuple[dict[str, Any], str]:
    """Run inspect-evals-lint over the packages holding the task files; returns its JSON document and the linter version.

    The linter's ``register`` preset and layout rule apply, so the result is
    the one ``inspect-evals-lint --preset register --task <path>`` gives. The
    document carries the linter's own ``score``, which the publisher checks
    against its stdlib-only recomputation.
    """
    # Imported here so the register helpers stay usable (and testable) without
    # the linter installed.
    from inspect_evals_lint import lint_task_files

    document = lint_task_files(root, task_paths).to_dict()
    # The clone lives in a temporary directory; its path says nothing about the entry.
    document.pop("root", None)
    return document, linter_version()


# ── Per-entry driver ────────────────────────────────────────────────────────


def describe_error(error: BaseException, clone_dir: Path) -> str:
    """``TypeName: message`` with the temporary clone path replaced, so the record names the repository, not the runner's disk."""
    text = f"{type(error).__name__}: {error}"
    for prefix in {str(clone_dir), str(clone_dir.resolve())}:
        text = text.replace(prefix, "<repository>")
    return text


def check_entry(
    entry: RegisterEntry, clone_dir: Path, timeout: int = 180
) -> EntryResult:
    result = EntryResult(
        id=entry.id,
        repository_url=entry.repository_url,
        commit=entry.commit,
        task_paths=entry.task_paths,
        status="error",
        checked_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    try:
        clone_at_commit(entry.repository_url, entry.commit, clone_dir, timeout)
    except CloneError as e:
        result.status, result.error = "clone_failed", str(e)
        return result
    try:
        layouts = derive_layouts(clone_dir, entry.task_paths)
    except LayoutError as e:
        result.status, result.error = "unsupported_layout", str(e)
        return result
    result.layouts = [asdict(layout) for layout in layouts]
    try:
        result.lint, result.lint_version = lint_task_paths(clone_dir, entry.task_paths)
    except Exception as e:  # a linter crash on one repo must not sink the run
        # Includes the linter's ConfigError for a repository whose suppression
        # comments use syntax the pinned release no longer accepts.
        result.error = describe_error(e, clone_dir)
        return result
    # The linter scores the document itself since 0.5.0; the publisher's
    # stdlib-only summarise() must agree with it, and the publisher checks.
    result.score = result.lint.get("score") or summarise(result.lint)
    result.status = "linted"
    return result


# ── Output ──────────────────────────────────────────────────────────────────


# ── Main ────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--output-dir", type=Path, default=Path("register-lint-output"))
    parser.add_argument("--register-dir", type=Path, default=REGISTER_DIR)
    parser.add_argument("--registry-commit", required=True)
    parser.add_argument("--runner-commit", required=True)
    parser.add_argument(
        "--filter",
        dest="filters",
        action="append",
        default=[],
        metavar="GLOB",
        help="Only entries whose id matches (repeatable)",
    )
    parser.add_argument(
        "--clone-dir",
        type=Path,
        default=None,
        help="Keep clones under this directory instead of a temporary one",
    )
    parser.add_argument(
        "--timeout", type=int, default=180, help="Seconds allowed per git command"
    )
    args = parser.parse_args(argv)

    for commit in (args.registry_commit, args.runner_commit):
        if not COMMIT_RE.fullmatch(commit):
            parser.error("Registry and runner commits must be full 40-character SHAs")

    entries = load_register_entries(args.register_dir, args.filters)
    if not entries:
        parser.error("No register entries matched")
    print(f"Checking {len(entries)} register entries", file=sys.stderr)

    results: list[EntryResult] = []
    with tempfile.TemporaryDirectory(prefix="register-lint-") as tmp:
        clone_root = args.clone_dir or Path(tmp)
        for entry in entries:
            result = check_entry(entry, clone_root / entry.id, args.timeout)
            if result.status == "linted" and result.score:
                note = f"{result.score['passing']}/{result.score['applicable']}"
            else:
                note = f"{result.status}: {result.error}"
            print(f"  {entry.id}: {note}", file=sys.stderr)
            results.append(result)
            if args.clone_dir is None:
                shutil.rmtree(clone_root / entry.id, ignore_errors=True)

    _write_json(
        args.output_dir / "results.json",
        {
            "schema_version": SCHEMA_VERSION,
            "registry": {
                "repository_url": REGISTRY_URL,
                "commit": args.registry_commit,
            },
            "runner_commit": args.runner_commit,
            "lint": {
                "version": linter_version(),
                "preset": "register",
                "policy": POLICY,
            },
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "entries": [asdict(result) for result in results],
        },
    )
    linted = sum(1 for r in results if r.status == "linted")
    print(
        f"Done: {linted}/{len(results)} entries linted; output in {args.output_dir}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
