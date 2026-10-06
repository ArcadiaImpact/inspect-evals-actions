# Inspect Evals Actions

This repository hosts some of the **CI/CD workflows** for [Inspect Evals](https://github.com/UKGovernmentBEIS/inspect_evals/tree/main).

It is designed to:

- Run the main build and test pipelines in a controlled environment
- Provide faster or more stable runners than the upstream repo

Evaluation tests are maintained in Inspect Evals. This repository contains the workflow helpers and tests for those helpers.

## Nightly CI failure triage

Scheduled Linux and Windows smoke and heavy-test failures dispatch a `ci-failure-triage` event to [`Generality-Labs/bienehito-experimental`](https://github.com/Generality-Labs/bienehito-experimental). The event includes the exact failing job URL and check results. That repository's agentic workflow finds or creates a tracking issue there. Existing Slack and `inspect_evals` failure notifications continue to run.

Maintainers must add the `CI_TRIAGE_DISPATCH_TOKEN` Actions secret to this repository. It should be a fine-grained personal access token limited to `Generality-Labs/bienehito-experimental` with **Contents: read and write**, so the workflow can send `repository_dispatch` to that private repository. The receiving `ci-failure-triage` workflow must be on its default branch. Manual test runs do not send triage events.

---

## Register lint service

The [Register Lint workflow](.github/workflows/register-lint.yml) reads the register from `UKGovernmentBEIS/inspect_evals` daily at 05:17 UTC. It records the register commit, fetches each upstream repository at its registered commit, and runs the pinned [inspect-evals-lint](https://github.com/Generality-Labs/inspect-evals-lint) release (`pyproject.toml`, `register-lint` group) with its register configuration: the `single-eval` layout preset with `eval.yaml` optional, since the register entry holds the metadata. Changes to registrations appear after the next daily run. Maintainers can also run the workflow manually.

The collector reads source files without installing, importing or executing evaluation code. It accepts HTTPS GitHub repository URLs, disables Git hooks and symlinks, and has a read-only token. A separate job validates a single JSON artifact and generates the public files. That job checks out only the reviewed operations code on `main` and uses this repository's `GITHUB_TOKEN` to replace the `register-lint` results branch. It does not write to `inspect_evals` or any evaluation repository. PR runs execute the helper tests; they do not collect or publish results. Filtered manual runs retain an artifact but do not replace the public results.

Results are informational. Counts are `passing / applicable` rules, one status per rule per package (the worst it reported, since a rule reports one finding per site): `pass` and `warn` count as passing, `fail` counts against the total, and `skip` is excluded. `suppressed` counts against the total under the `register-v1` policy (inspect-evals-lint JSON schema 1 and 2) and as passing under `register-v2` (schema 3). The collector picks the policy from the schema the pinned linter writes; the publisher rejects a report whose schema does not match the policy, and an unknown schema version. When any rule was suppressed, the count is shown beside the score in the summary table, the collector log and on the badges (`16/17 · 2 suppressed`), and repository suppressions remain visible in the full report. Since inspect-evals-lint 0.5.0 the linter computes this score itself and the collector records it; the publisher, which runs with the standard library only, recomputes it and rejects a document where the two differ. Repositories whose task files are outside a Python package are reported as `unsupported_layout`; clone and linter errors have separate statuses. A repository whose suppression comments use the `noautolint` syntax that inspect-evals-lint 0.3.0 removed is still linted: since 0.4.1 each such marker is a `suppression_syntax` warning naming the replacement, and the findings it used to cover are reported under their own rules.

### Public files

- `summary.json` contains schema version 1, generation time, the registry URL and commit, the runner commit, the linter version, preset and policy, and one summary per entry.
- `results/<id>.json` contains the upstream URL, commit, task paths, check time, detected layouts and full check report.
- `badges/<id>/lint.json` and the five category files provide Shields endpoint documents.
- `README.md` provides a results table and badge instructions.

The files are served from `https://raw.githubusercontent.com/ArcadiaImpact/inspect-evals-actions/register-lint/`. The Inspect Evals docs fetch `summary.json` in the browser and compare each result's repository, commit and task paths with the registrations included in the docs build. The schema and the policy (`register-v1` or `register-v2`, see above) identify the contract; changes to score semantics require a policy update and a corresponding consumer update, and the Inspect Evals docs must accept a new policy before a pin bump publishes it. The package version remains pinned in `pyproject.toml` and `uv.lock`.

Replace `<id>` with the register directory name to embed a badge:

```markdown
![inspect-evals lint](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/ArcadiaImpact/inspect-evals-actions/register-lint/badges/<id>/lint.json)
```

Category badges use `file_structure.json`, `code_quality.json`, `tests.json`, `best_practices.json` and `security.json` in the same directory. Badges describe the last collected registered commit. The docs table also checks whether the registration has changed or the result is more than seven days old.

Lint JSON schema version 2 added the `security` category; reports without security checks show `no checks` on that badge. Schema version 3 counts suppressed rules as passing and is published under `register-v2`. The register service's artifact and summary formats remain at version 1; the nested lint report has its own version.

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
