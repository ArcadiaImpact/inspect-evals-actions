#!/usr/bin/env bash
set -eu

usage() {
	echo "Summarise a smoke test log"
	echo "Usage: $0 <log_file> <summary_title>"
	exit 1
}

log_file="${1}"
summary_title="${2}"

if [[ ! -f "$log_file" ]]; then
	usage
fi

# The descriptor format emitted by tools/run_evals.py is:
#   "eval N (EVAL_ID) task M of K (TASK_NAME)"
# We extract TASK_NAME by matching the 'task M of K (TASK_NAME)' portion,
# which appears in every relevant log line.
extract_task_name='s/.*task [0-9]+ of [0-9]+ \(([^)]+)\).*/\1/p'

# Total --> {success, not success}
total=$(grep "Testing eval" "$log_file" | sed -nE "$extract_task_name")
successes=$(grep "Succeeded:" "$log_file" | sed -nE "$extract_task_name")
not_successes=$(comm -23 <(echo "$total" | sort) <(echo "$successes" | sort) || true)

# Not success --> {acceptable, expected, timeouts, unexpected}
accepted_errors=$(grep "ignoring" "$log_file" | sed -nE "$extract_task_name" || true)
a_priori_expected=$(grep "Skipping eval" "$log_file" | sed -nE "$extract_task_name" || true)
timeouts=$(grep "Timed out:" "$log_file" | sed -nE "$extract_task_name" || true)
unexpected_errors=$(grep "is not considered" "$log_file" | sed -nE "$extract_task_name" || true)

# Emitted by tools/run_evals.py when REQUIRE_HF_ACCESS=1 and a dataset denies access:
#   "Hugging Face access denied on <descriptor>: dataset REPO_ID (accept the terms at URL)"
# or "...: dataset unknown" when the repo id could not be parsed. The line sits
# inside a logging line, so match the substring.
access_denied_lines=$(grep "Hugging Face access denied on" "$log_file" || true)

n_total=$(echo "$total" | grep -c . || true)
n_total=${n_total:-0}
n_success=$(echo "$successes" | grep -c . || true)
n_success=${n_success:-0}
n_not_success=$(echo "$not_successes" | grep -c . || true)
n_not_success=${n_not_success:-0}
n_accepted=$(echo "$accepted_errors" | grep -c . || true)
n_accepted=${n_accepted:-0}
n_skipped=$(echo "$a_priori_expected" | grep -c . || true)
n_skipped=${n_skipped:-0}
n_timeouts=$(echo "$timeouts" | grep -c . || true)
n_timeouts=${n_timeouts:-0}
n_unexpected=$(echo "$unexpected_errors" | grep -c . || true)
n_unexpected=${n_unexpected:-0}
n_access_denied=$(echo "$access_denied_lines" | grep -c . || true)
n_access_denied=${n_access_denied:-0}

summary=$(
	cat <<EOF
*$summary_title*
- *Total evals:* $n_total
- *Successes:* $n_success
- *Not-successes:* $n_not_success
    - Accepted errors: $n_accepted
    - Expected skips: $n_skipped
    - Timeouts: $n_timeouts
    - Unexpected errors: $n_unexpected
    - Hugging Face access denied: $n_access_denied
EOF
)

if [ "$n_unexpected" -gt 0 ]; then
	bullet_list=""
	while IFS= read -r task; do
		bullet_list+=$'- '"$task"$'\n'
	done <<<"$unexpected_errors"

	summary+=$'\n\n*Tasks with unexpected errors:*\n'
	summary+="$bullet_list"
fi

if [ "$n_access_denied" -gt 0 ]; then
	access_list=""
	while IFS= read -r line; do
		task=$(echo "$line" | sed -nE "$extract_task_name")
		repo_id=$(echo "$line" | sed -nE 's/.*: dataset ([^ ]+).*/\1/p')
		if [ -n "$repo_id" ] && [ "$repo_id" != "unknown" ]; then
			access_list+=$'- '"$task"$': https://huggingface.co/datasets/'"$repo_id"$'\n'
		else
			access_list+=$'- '"$task"$': dataset unknown\n'
		fi
	done <<<"$access_denied_lines"

	summary+=$'\n\n*Hugging Face access denied (accept the terms; no code fix):*\n'
	summary+="$access_list"
fi

echo "$summary"

# Unexpected errors or denied dataset access imply a failure
if [ "$n_unexpected" -gt 0 ] || [ "$n_access_denied" -gt 0 ]; then
	exit 1
fi
