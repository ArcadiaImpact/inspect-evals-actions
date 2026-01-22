#!/usr/bin/env bash
set -eu

usage() {
  echo "Usage: $0 log_file"
  exit 1
}

log_file="${1:-}"

if [[ -z "$log_file" || ! -f "$log_file" ]]; then
  usage
fi

stale_tasks=$(grep "WARNING:__main__:Task task_name=" "$log_file" \
              | grep "is in SKIPPABLE_TASKS, but should be removed" \
              | sed -E "s/.*task_name='([^']+)'.*/\1/" || true)

n_stale=$(echo "$stale_tasks" | grep -c . 2>/dev/null || true)
n_stale=${n_stale:-0}

if [ "$n_stale" -gt 0 ]; then
    echo "*Found evals that are being skipped that do not need to be skipped:*"
    while IFS= read -r task; do
        echo "• $task"
    done <<< "$stale_tasks"
    exit 1
fi