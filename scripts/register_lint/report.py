"""Public JSON, badges and summaries for the register lint service."""

from __future__ import annotations

import html
import json
import re
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REGISTRY_URL = "https://github.com/UKGovernmentBEIS/inspect_evals"
POLICY = "register-v1"
SCHEMA_VERSION = 1

BADGE_LABEL = "inspect-evals lint"
CATEGORY_LABELS = {
    "file_structure": "lint: structure",
    "code_quality": "lint: code quality",
    "tests": "lint: tests",
    "best_practices": "lint: best practices",
}
STATUS_KEYS = ("pass", "fail", "warn", "skip", "suppressed")
RULE_STATUS_ORDER = ("fail", "warn", "suppressed", "pass", "skip")
"""Worst first: a rule's status is the first of these it reported anywhere in a package.

The same order as ``inspect_evals_lint.RULE_STATUS_ORDER``. The publisher runs
with the standard library only, so it cannot import the linter; it recomputes
the linter's ``score`` with this copy and rejects a document where they differ.
"""
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")

# Same thresholds as inspect-evals-lint's own compliance summary.
SCORE_GREEN = 0.80
SCORE_YELLOW = 0.50


@dataclass
class EntryResult:
    id: str
    repository_url: str
    commit: str
    task_paths: list[str]
    status: str  # linted | clone_failed | unsupported_layout | error
    checked_at: str
    error: str | None = None
    lint_version: str | None = None
    layouts: list[dict[str, str]] = field(default_factory=list)
    score: dict[str, Any] | None = None
    lint: dict[str, Any] | None = None


def rule_statuses(package: dict[str, Any]) -> list[tuple[str, str, str]]:
    """``(rule, category, status)`` once per rule that reported on a package.

    inspect-evals-lint reports one ``outcome`` for a rule that passed or did not
    apply and one ``diagnostic`` per site a rule found something at, so a rule
    can appear several times. Scores count each rule once, at the worst status
    it reported, which keeps ``passing / applicable`` a count of rules.
    """
    seen: dict[str, tuple[str, set[str]]] = {}
    for item in (*package.get("outcomes", []), *package.get("diagnostics", [])):
        rule = item.get("rule") or "<unknown>"
        category, statuses = seen.setdefault(
            rule, (item.get("category") or "other", set())
        )
        statuses.add(item["status"])
    out: list[tuple[str, str, str]] = []
    for rule, (category, statuses) in seen.items():
        status = next((s for s in RULE_STATUS_ORDER if s in statuses), None)
        if status is not None:
            out.append((rule, category, status))
    return out


def summarise(lint_doc: dict[str, Any]) -> dict[str, Any]:
    """Score and per-category counts for one register entry's lint document."""
    overall = dict.fromkeys(STATUS_KEYS, 0)
    by_category: dict[str, dict[str, int]] = {}
    for package in lint_doc.get("packages", []):
        for _rule, category, status in rule_statuses(package):
            overall[status] += 1
            counts = by_category.setdefault(category, dict.fromkeys(STATUS_KEYS, 0))
            counts[status] += 1

    def scored(counts: dict[str, int]) -> dict[str, Any]:
        applicable = (
            counts["pass"] + counts["fail"] + counts["warn"] + counts["suppressed"]
        )
        passing = counts["pass"] + counts["warn"]
        return {
            **counts,
            "applicable": applicable,
            "passing": passing,
            "score": round(passing / applicable, 4) if applicable else None,
        }

    return {
        **scored(overall),
        "by_category": {
            name: scored(counts) for name, counts in sorted(by_category.items())
        },
    }


# ── Badges ──────────────────────────────────────────────────────────────────


def badge(
    label: str, score: dict[str, Any] | None, unavailable: str | None = None
) -> dict[str, Any]:
    """A shields.io endpoint document."""
    if unavailable is not None or score is None:
        return {
            "schemaVersion": 1,
            "label": label,
            "message": unavailable or "unavailable",
            "color": "lightgrey",
        }
    if not score["applicable"]:
        return {
            "schemaVersion": 1,
            "label": label,
            "message": "no checks",
            "color": "lightgrey",
        }
    ratio = score["passing"] / score["applicable"]
    if ratio == 1.0:
        color = "brightgreen"
    elif ratio >= SCORE_GREEN:
        color = "green"
    elif ratio >= SCORE_YELLOW:
        color = "yellow"
    else:
        color = "red"
    return {
        "schemaVersion": 1,
        "label": label,
        "message": f"{score['passing']}/{score['applicable']}",
        "color": color,
    }


UNAVAILABLE_MESSAGES = {
    "clone_failed": "clone failed",
    "unsupported_layout": "layout unsupported",
    "error": "error",
}


def badges_for(result: EntryResult) -> dict[str, dict[str, Any]]:
    """``{relative path: badge document}`` for one entry."""
    unavailable = (
        None
        if result.status == "linted"
        else UNAVAILABLE_MESSAGES.get(result.status, "unavailable")
    )
    out = {
        f"badges/{result.id}/lint.json": badge(BADGE_LABEL, result.score, unavailable)
    }
    for category, label in CATEGORY_LABELS.items():
        category_score = (result.score or {}).get("by_category", {}).get(category)
        if unavailable is None and category_score is None:
            category_score = {
                "passing": 0,
                "applicable": 0,
            }  # linted, but nothing in this section
        out[f"badges/{result.id}/{category}.json"] = badge(
            label, category_score, unavailable
        )
    return out


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )


def _table_cell(text: str) -> str:
    """Flatten ``text`` onto one line and escape pipes so it cannot break a markdown table row.

    Clone errors are raw git stderr, which is often multi-line and may contain ``|``.
    """
    return html.escape(" ".join(text.split())).replace("|", "\\|")


def render_summary_markdown(
    results: list[EntryResult], badge_base_url: str | None
) -> str:
    lines = [
        "# Register lint results",
        "",
        "Static checks from [inspect-evals-lint](https://github.com/Generality-Labs/inspect-evals-lint) run against each register entry's upstream repository at its pinned commit. "
        "Score is passing/applicable checks; warnings pass, suppressed checks do not, skipped checks are not applicable.",
        "",
        "| Eval | Status | Score | Structure | Code quality | Tests | Best practices | Commit |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in sorted(results, key=lambda r: r.id):
        if r.status == "linted" and r.score:
            cells = [f"{r.score['passing']}/{r.score['applicable']}"]
            for category in CATEGORY_LABELS:
                c = r.score["by_category"].get(category)
                cells.append(
                    f"{c['passing']}/{c['applicable']}"
                    if c and c["applicable"]
                    else "-"
                )
            status = "linted"
        else:
            cells = ["-"] * 5
            status = f"{r.status}: {_table_cell(r.error)}" if r.error else r.status
        commit = f"[`{r.commit[:7]}`]({r.repository_url}/tree/{r.commit})"
        lines.append(f"| {r.id} | {status} | " + " | ".join(cells) + f" | {commit} |")
    if badge_base_url:
        lines += [
            "",
            "## Embedding a badge",
            "",
            "Replace `<id>` with the register entry id; `lint.json` may be swapped for `file_structure.json`, `code_quality.json`, `tests.json` or `best_practices.json`.",
            "",
            "```markdown",
            f"![inspect-evals lint](https://img.shields.io/endpoint?url={badge_base_url}/badges/<id>/lint.json)",
            "```",
        ]
    return "\n".join(lines) + "\n"


def write_outputs(
    results: list[EntryResult],
    output_dir: Path,
    badge_base_url: str | None,
    provenance: dict[str, Any],
) -> None:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    for r in results:
        _write_json(output_dir / "results" / f"{r.id}.json", asdict(r))
        for rel_path, doc in badges_for(r).items():
            _write_json(output_dir / rel_path, doc)
    _write_json(
        output_dir / "summary.json",
        {
            **provenance,
            "entries": [
                {
                    "id": r.id,
                    "status": r.status,
                    "error": r.error,
                    "repository_url": r.repository_url,
                    "commit": r.commit,
                    "task_paths": r.task_paths,
                    "checked_at": r.checked_at,
                    "score": None
                    if r.score is None
                    else {k: v for k, v in r.score.items() if k != "by_category"},
                    "by_category": None if r.score is None else r.score["by_category"],
                }
                for r in sorted(results, key=lambda r: r.id)
            ],
        },
    )
    (output_dir / "README.md").write_text(
        render_summary_markdown(results, badge_base_url), encoding="utf-8"
    )
