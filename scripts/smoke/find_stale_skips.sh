#!/usr/bin/env bash
set -eu

usage() {
  echo "Usage: $0 <log_file> <summary_title>"
  exit 1
}

log_file="${1}"
summary_title="${2}"

if [[ ! -f "$log_file" ]]; then
  usage
fi

stale_tasks=$(grep "WARNING:__main__:Task task_name=" "$log_file" \
              | grep "is in SKIPPABLE_TASKS, but should be removed" \
              | sed -E "s/.*task_name='([^']+)'.*/\1/" || true)

n_stale=$(echo "$stale_tasks" | grep -c . 2>/dev/null || true)
n_stale=${n_stale:-0}

if [ "$n_stale" -gt 0 ]; then
    report="*$summary_title*"
    while IFS= read -r task; do
        report+=$'\n- '"$task"
    done <<< "$stale_tasks"

    # stdout feeds the Slack message (the workflow redirects it to a file), so it
    # never reaches the Actions step log. Re-emit the report to stderr (plus a
    # pointer to the source logs) so the failing step explains itself.
    echo "$report"
    {
        echo "$report"
        echo
        echo "These tasks are listed in SKIPPABLE_TASKS but ran successfully, so the"
        echo "skip is stale and should be removed. See the 'Smoke test' job logs for"
        echo "the per-task warnings."
    } >&2
    exit 1
fi