#!/usr/bin/env bash
set -eu

usage() {
  echo "Summarise a smoke test log"
  echo "Usage: $0 log_file"
  exit 1
}

log_file="${1:-}"

if [[ -z "$log_file" || ! -f "$log_file" ]]; then
  usage
fi

# Total --> {success, not success}
total=$(grep "Testing eval" "$log_file" | sed -E 's/.*Testing eval [0-9]+: //')
successes=$(grep succeeded "$log_file" | sed -E 's/.*succeeded: //')
not_successes=$(comm -23 <(echo "$total" | sort) <(echo "$successes" | sort) || true)

# Not success --> {acceptable, expected, timeouts, unexpected}
accepted_errors=$(grep "ignoring" "$log_file" | sed -E "s/.*on task_name='([^']+)'.*/\1/" || true)
a_priori_expected=$(grep "Skipping eval" "$log_file" | sed -E 's/.*Skipping eval [0-9]+: ([^\.]+)\..*/\1/' || true)
timeouts=$(grep 'timed out:' "$log_file" | sed -E 's/.*timed out: ([^ ]+).*/\1/' || true)
unexpected_errors=$(grep "is not considered" "$log_file" | sed -E "s/.*on task task_name='([^']+)'.*/\1/" || true)

n_total=$(echo "$total" | grep -c . || echo 0)
n_success=$(echo "$successes" | grep -c . || echo 0)
n_not_success=$(echo "$not_successes" | grep -c . || echo 0)
n_accepted=$(echo "$accepted_errors" | grep -c . || echo 0)
n_skipped=$(echo "$a_priori_expected" | grep -c . || echo 0)
n_timeouts=$(echo "$timeouts" | grep -c . || echo 0)
n_unexpected=$(echo "$unexpected_errors" | grep -c . || echo 0)
n_unexpected=${n_unexpected:-0}

summary=$(cat <<EOF
*Smoke Test Summary*
• *Total evals:* $n_total
• *Successes:* $n_success
• *Not-successes:* $n_not_success
    ◦ Accepted errors: $n_accepted
    ◦ Expected skips: $n_skipped
    ◦ Timeouts: $n_timeouts
    ◦ Unexpected errors: $n_unexpected
EOF
)

if [ "$n_unexpected" -gt 0 ]; then
  bullet_list=""
  while IFS= read -r task; do
    bullet_list+=$'• '"$task"$'\n'
  done <<< "$unexpected_errors"

  summary+=$'\n\n*Tasks with unexpected errors:*\n'
  summary+="$bullet_list"
fi

echo "$summary"

# Unexpected errors implies a failure
if [ "$n_unexpected" -gt 0 ]; then
  exit 1
fi