#!/usr/bin/env python3
"""Dispatch a failed scheduled CI job to the private issue triage workflow."""

import json
import os
import sys
import urllib.error
import urllib.request


SOURCE_REPO = "ArcadiaImpact/inspect-evals-actions"
TARGET_REPO = "Generality-Labs/bienehito-experimental"


def api_request(url, token, payload=None):
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers=headers,
        method="POST" if payload is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response) if payload is None else None


def main():
    if len(sys.argv) != 3:
        raise ValueError("usage: dispatch_ci_triage.py <suite> <job name>")
    suite, job_name = sys.argv[1:]
    if os.environ.get("GITHUB_REPOSITORY") != SOURCE_REPO:
        raise ValueError("CI triage dispatch must run in the source repository")
    run_id = os.environ["GITHUB_RUN_ID"]
    if not run_id.isdecimal():
        raise ValueError("invalid GITHUB_RUN_ID")
    read_token = os.environ.get("GITHUB_TOKEN")
    dispatch_token = os.environ.get("CI_TRIAGE_DISPATCH_TOKEN")
    if not read_token or not dispatch_token:
        raise ValueError("GITHUB_TOKEN and CI_TRIAGE_DISPATCH_TOKEN are required")

    jobs = api_request(
        f"https://api.github.com/repos/{SOURCE_REPO}/actions/runs/{run_id}/jobs?per_page=100",
        read_token,
    )["jobs"]
    job_urls = [job["html_url"] for job in jobs if job.get("name") == job_name]
    if len(job_urls) != 1:
        raise ValueError(f"expected one matching CI job named {job_name!r}; got {len(job_urls)}")
    job_url = job_urls[0]
    expected_prefix = f"https://github.com/{SOURCE_REPO}/actions/runs/{run_id}/job/"
    if not job_url.startswith(expected_prefix) or not job_url[len(expected_prefix):].isdecimal():
        raise ValueError("GitHub returned an unexpected job URL")

    failures = [
        check.replace("_", " ")
        for item in os.environ.get("CHECK_RESULTS", "").split(",")
        if "=" in item
        for check, result in [item.split("=", 1)]
        if result == "failure"
    ]
    if not failures:
        raise ValueError("no failed checks were passed to CI triage")
    payload = {
        "event_type": "ci-failure-triage",
        "client_payload": {
            "suite": suite,
            "job_url": job_url,
            "failure_kind": ", ".join(failures),
            "message": f"Triage following failing test {job_url}",
        },
    }
    api_request(f"https://api.github.com/repos/{TARGET_REPO}/dispatches", dispatch_token, payload)
    print(f"Dispatched CI triage for {job_url}")


if __name__ == "__main__":
    try:
        main()
    except (KeyError, ValueError, urllib.error.HTTPError, urllib.error.URLError) as exc:
        print(f"CI triage dispatch failed: {exc}", file=sys.stderr)
        sys.exit(1)
