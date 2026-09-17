"""Validate the worker artifact and generate the files allowed on the results branch.

This module uses only the standard library. It never copies artifact paths or
uses artifact strings as commands, templates, or executable content.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from .report import (
    CATEGORY_LABELS,
    COMMIT_RE,
    POLICY,
    REGISTRY_URL,
    SCHEMA_VERSION,
    STATUS_KEYS,
    EntryResult,
    summarise,
    write_outputs,
)

MAX_ARTIFACT_BYTES = 20 * 1024 * 1024
ID_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,99}")
REPOSITORY_RE = re.compile(
    r"https://github\.com/[A-Za-z0-9][A-Za-z0-9-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}"
)


def validate_id(value: str) -> None:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ValueError("Invalid register entry id")


def validate_repository_url(value: str) -> None:
    if not isinstance(value, str) or not REPOSITORY_RE.fullmatch(value):
        raise ValueError("repository_url must be an HTTPS GitHub repository URL")


def validate_commit(value: Any) -> None:
    if not isinstance(value, str) or not COMMIT_RE.fullmatch(value):
        raise ValueError("Expected a full 40-character commit SHA")


def validate_timestamp(value: Any) -> None:
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("Invalid timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("Timestamp must include a timezone")


def validate_task_paths(value: Any) -> None:
    if not isinstance(value, list) or not 1 <= len(value) <= 1000:
        raise ValueError("Expected task paths")
    for item in value:
        if (
            not isinstance(item, str)
            or not item
            or len(item) > 1000
            or "\\" in item
            or any(ord(c) < 32 for c in item)
            or PurePosixPath(item).is_absolute()
            or ".." in PurePosixPath(item).parts
        ):
            raise ValueError("Invalid task path")


def validate_lint(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or not isinstance(value.get("evaluations"), list):
        raise ValueError("Expected a lint report")
    for evaluation in value["evaluations"]:
        if not isinstance(evaluation, dict) or not isinstance(
            evaluation.get("results"), list
        ):
            raise ValueError("Expected check results")
        for check in evaluation["results"]:
            if (
                not isinstance(check, dict)
                or check.get("status") not in STATUS_KEYS
                or check.get("category") not in CATEGORY_LABELS
                or not isinstance(check.get("check"), str)
                or not isinstance(check.get("message"), str)
            ):
                raise ValueError("Invalid check result")
    return value


def validate_document(doc: Any) -> tuple[list[EntryResult], dict[str, Any]]:
    if not isinstance(doc, dict) or set(doc) != {
        "schema_version",
        "registry",
        "runner_commit",
        "lint",
        "generated_at",
        "entries",
    }:
        raise ValueError("Unexpected artifact fields")
    if (
        type(doc["schema_version"]) is not int
        or doc["schema_version"] != SCHEMA_VERSION
    ):
        raise ValueError("Unsupported schema version")
    registry = doc["registry"]
    if not isinstance(registry, dict) or set(registry) != {"repository_url", "commit"}:
        raise ValueError("Invalid registry")
    if registry["repository_url"] != REGISTRY_URL:
        raise ValueError("Unexpected registry repository")
    validate_commit(registry["commit"])
    validate_commit(doc["runner_commit"])
    validate_timestamp(doc["generated_at"])
    policy = doc["lint"]
    if (
        not isinstance(policy, dict)
        or set(policy) != {"version", "preset", "policy"}
        or policy["preset"] != "register"
        or policy["policy"] != POLICY
        or not isinstance(policy["version"], str)
        or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", policy["version"])
    ):
        raise ValueError("Invalid lint policy")
    if not isinstance(doc["entries"], list) or not 1 <= len(doc["entries"]) <= 10000:
        raise ValueError("Expected register entries")
    results = []
    seen = set()
    for entry in doc["entries"]:
        if not isinstance(entry, dict) or set(entry) != set(
            EntryResult.__dataclass_fields__
        ):
            raise ValueError("Unexpected result fields")
        validate_id(entry["id"])
        if entry["id"] in seen:
            raise ValueError("Duplicate register entry")
        seen.add(entry["id"])
        validate_repository_url(entry["repository_url"])
        validate_commit(entry["commit"])
        validate_task_paths(entry["task_paths"])
        validate_timestamp(entry["checked_at"])
        if entry["error"] is not None and not isinstance(entry["error"], str):
            raise ValueError("Invalid error message")
        if not isinstance(entry["layouts"], list):
            raise ValueError("Invalid layouts")
        if entry["status"] == "linted":
            if entry["lint_version"] != policy["version"]:
                raise ValueError("Inconsistent lint version")
            # Recompute the public counts from validated checks.
            score = summarise(validate_lint(entry["lint"]))
            if score != entry["score"]:
                raise ValueError("Inconsistent lint counts")
            entry = {**entry, "score": score}
        elif entry["status"] in {"clone_failed", "unsupported_layout", "error"}:
            if entry["score"] is not None or entry["lint"] is not None:
                raise ValueError("Unavailable results cannot have a score")
        else:
            raise ValueError("Unknown result status")
        results.append(EntryResult(**entry))
    return results, {key: value for key, value in doc.items() if key != "entries"}


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def reject_constant(value: str) -> Any:
    raise ValueError(f"Invalid JSON constant: {value}")


def publish(artifact_dir: Path, output_dir: Path, badge_base_url: str) -> None:
    if artifact_dir.is_symlink() or set(p.name for p in artifact_dir.iterdir()) != {
        "results.json"
    }:
        raise ValueError("Artifact must contain only results.json")
    source = artifact_dir / "results.json"
    if (
        source.is_symlink()
        or not source.is_file()
        or source.stat().st_size > MAX_ARTIFACT_BYTES
    ):
        raise ValueError("Invalid artifact file")
    if output_dir.exists() or output_dir.is_symlink():
        raise ValueError("Output directory must be new")
    doc = json.loads(
        source.read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicate_keys,
        parse_constant=reject_constant,
    )
    results, provenance = validate_document(doc)
    write_outputs(results, output_dir, badge_base_url, provenance)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--badge-base-url", required=True)
    args = parser.parse_args()
    publish(args.artifact_dir, args.output_dir, args.badge_base_url)


if __name__ == "__main__":
    main()
