# Inspect Evals Actions

This repository hosts some of the **CI/CD workflows** for [Inspect Evals](https://github.com/UKGovernmentBEIS/inspect_evals/tree/main).  

It is designed to:

- Run the main build and test pipelines in a controlled environment  
- Provide faster or more stable runners than the upstream repo  

Evaluation tests are maintained in Inspect Evals. This repository contains the workflow helpers and tests for those helpers.

---

## Register lint service

The [Register Lint workflow](.github/workflows/register-lint.yml) reads the register from `UKGovernmentBEIS/inspect_evals` daily at 05:17 UTC. It records the register commit, fetches each upstream repository at its registered commit, and runs `inspect-evals-lint==0.1.1` with the `register` preset. Changes to registrations appear after the next daily run. Maintainers can also run the workflow manually.

The collector reads source files without installing, importing or executing evaluation code. It accepts HTTPS GitHub repository URLs, disables Git hooks and symlinks, and has a read-only token. A separate job validates a single JSON artifact and generates the public files. That job checks out only the reviewed operations code on `main` and uses this repository's `GITHUB_TOKEN` to replace the `register-lint` results branch. It does not write to `inspect_evals` or any evaluation repository. PR runs execute the helper tests; they do not collect or publish results. Filtered manual runs retain an artifact but do not replace the public results.

Results are informational. Counts are `passing / applicable`: `pass` and `warn` count as passing, `fail` and `suppressed` count against the total, and `skip` is excluded. Repository suppressions remain visible in the full report. Repositories whose task files are outside a Python package are reported as `unsupported_layout`; clone and linter errors have separate statuses.

### Public files

- `summary.json` contains schema version 1, generation time, the registry URL and commit, the runner commit, the linter version, preset and policy, and one summary per entry.
- `results/<id>.json` contains the upstream URL, commit, task paths, check time, detected layouts and full check report.
- `badges/<id>/lint.json` and the four category files provide Shields endpoint documents.
- `README.md` provides a results table and badge instructions.

The files are served from `https://raw.githubusercontent.com/ArcadiaImpact/inspect-evals-actions/register-lint/`. The Inspect Evals docs fetch `summary.json` in the browser and compare each result's repository, commit and task paths with the registrations included in the docs build. The schema and `register-v1` policy identify the contract; changes to score semantics require a policy update and a corresponding consumer update. The package version remains pinned in `pyproject.toml` and `uv.lock`.

Replace `<id>` with the register directory name to embed a badge:

```markdown
![inspect-evals lint](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/ArcadiaImpact/inspect-evals-actions/register-lint/badges/<id>/lint.json)
```

Category badges use `file_structure.json`, `code_quality.json`, `tests.json` and `best_practices.json` in the same directory. Badges describe the last collected registered commit. The docs table also checks whether the registration has changed or the result is more than seven days old.

### Local validation

```bash
uv sync --locked --group register-lint
uv run --locked --group register-lint python -m pytest tests
uv run actionlint
uv run zizmor --no-progress --persona=auditor --min-severity=low .github/workflows/
```

To collect a local registry checkout, supply its commit and the operations commit:

```bash
uv run --locked --group register-lint python -m scripts.register_lint.collect \
  --register-dir /path/to/inspect_evals/register \
  --registry-commit "$(git -C /path/to/inspect_evals rev-parse HEAD)" \
  --runner-commit "$(git rev-parse HEAD)" \
  --output-dir register-lint-artifact
python3 -m scripts.register_lint.publish \
  --artifact-dir register-lint-artifact \
  --output-dir register-lint-output \
  --badge-base-url https://raw.githubusercontent.com/ArcadiaImpact/inspect-evals-actions/register-lint
```

The publication command only creates local files. Its output directory must be new. The first public results become available after this workflow is merged and run on `main`; no additional cross-repository secret is needed.
