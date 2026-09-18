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
    pass


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

    The evaluation is the directory holding the task file. Its parent is the
    source root, and any enclosing packages between the source root and the
    repository root form the import prefix (``india_evals/safeguards/task.py``
    lints ``safeguards`` under ``india_evals`` with prefix ``india_evals``).
    """
    layouts: dict[str, EvalLayout] = {}
    for task_path in task_paths:
        task_file = (root / task_path).resolve()
        if not task_file.is_relative_to(root.resolve()):
            raise LayoutError(f"task_path escapes the repository: {task_path}")
        if not task_file.is_file():
            raise LayoutError(f"task_path not found at the pinned commit: {task_path}")
        eval_dir = task_file.parent
        if eval_dir == root.resolve() or not (eval_dir / "__init__.py").exists():
            raise LayoutError(
                f"{task_path} is not inside a package (no __init__.py next to it); "
                "inspect-evals-lint checks one package per evaluation"
            )
        source_root = eval_dir.parent
        prefix_parts: list[str] = []
        package = source_root
        while package != root.resolve() and (package / "__init__.py").exists():
            prefix_parts.insert(0, package.name)
            package = package.parent
        key = str(eval_dir.relative_to(root.resolve()))
        # Forward slashes keep the published JSON identical across runners.
        relative_source_root = source_root.relative_to(root.resolve())
        layouts.setdefault(
            key,
            EvalLayout(
                eval_name=eval_dir.name,
                source_root=relative_source_root.as_posix(),  # posix: noqa
                import_prefix=".".join(prefix_parts),
            ),
        )
    return list(layouts.values())


# ── Lint ────────────────────────────────────────────────────────────────────


def linter_version() -> str:
    """The version of the installed inspect-evals-lint, from the package itself.

    Both the document header and each entry record this, and the publisher
    rejects a document where they differ, so there must be exactly one source.
    """
    import inspect_evals_lint

    return inspect_evals_lint.__version__


def lint_layouts(root: Path, layouts: list[EvalLayout]) -> tuple[dict[str, Any], str]:
    """Run inspect-evals-lint over each layout; returns its JSON document and the linter version."""
    # Imported here so the register/layout helpers stay usable (and testable)
    # without the linter installed.
    from dataclasses import replace

    from inspect_evals_lint import PRESETS, lint_evaluation
    from inspect_evals_lint.output import reports_to_dict

    reports = []
    for layout in layouts:
        config = replace(
            PRESETS["register"],
            source_root=layout.source_root,
            import_prefix=layout.import_prefix,
        )
        reports.append(lint_evaluation(root, layout.eval_name, config))
    return reports_to_dict(reports, root), linter_version()


# ── Per-entry driver ────────────────────────────────────────────────────────


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
        result.lint, result.lint_version = lint_layouts(clone_dir, layouts)
    except Exception as e:  # a linter crash on one repo must not sink the run
        result.error = f"{type(e).__name__}: {e}"
        return result
    result.score = summarise(result.lint)
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
