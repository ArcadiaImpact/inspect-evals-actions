#!/usr/bin/env bash

set -eu


usage() {
  cat <<EOF
Usage: $0 <summary_file> <slack_webhook_url>

Sends a summary to a Slack channel using a webhook.

Arguments:
  summary_file       Path to a file containing the summary to send
  slack_webhook_url  Slack Incoming Webhook URL

Environment Variables:
  GITHUB_REPOSITORY  Optional. owner/repo (used to build GitHub Actions run URL)
  GITHUB_RUN_ID      Optional. Workflow run ID for GitHub Actions URL
  DRY_RUN            Optional. Log payload instead of sending.

Example:
  $0 summary.txt https://hooks.slack.com/services/XXXX/XXXX/XXXX
EOF
  exit 1
}

summary_file="${1:-}"
slack_webhook_url="${2:-}"

if [[ -z "$summary_file" || ! -f "$summary_file" ]]; then
  usage
fi

if [[ -z "$slack_webhook_url" ]]; then
    usage
fi

summary=$(<"$summary_file")

if [[ -n "${GITHUB_REPOSITORY:-}" && -n "${GITHUB_RUN_ID:-}" ]]; then
  run_url="<https://github.com/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}|View Run Details>"
else
  run_url="Run details are not visible. Invoked locally, so not associated with a CI run"
fi

payload=$(jq -n \
  --arg summary "$summary" \
  --arg run_url "$run_url" \
  '{
    blocks: [
      { type: "section", text: { type: "mrkdwn", text: $summary } },
      { type: "section", text: { type: "mrkdwn", text: $run_url } }
    ]
  }'
)

if [[ -n "${DRY_RUN:-}" ]]; then
    echo "$payload"
else
    curl -sS -X POST \
    -H 'Content-type: application/json' \
    --data "$payload" \
    "$slack_webhook_url"
fi
