import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "dispatch_ci_triage.py"
SPEC = importlib.util.spec_from_file_location("dispatch_ci_triage", SCRIPT)
dispatcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dispatcher)


class DispatchCITriageTest(unittest.TestCase):
    def setUp(self):
        self.url = (
            "https://github.com/ArcadiaImpact/inspect-evals-actions"
            "/actions/runs/123/job/456"
        )
        self.environment = {
            "GITHUB_REPOSITORY": "ArcadiaImpact/inspect-evals-actions",
            "GITHUB_RUN_ID": "123",
            "GITHUB_TOKEN": "read-token",
            "CI_TRIAGE_DISPATCH_TOKEN": "dispatch-token",
            "CHECK_RESULTS": "tests=failure,slow_check=success",
        }

    def test_dispatches_exact_job_with_failure_context(self):
        calls = []

        def fake_api(url, token, payload=None):
            calls.append((url, token, payload))
            if payload is None:
                return {"jobs": [
                    {"name": "Other job", "html_url": self.url.replace("456", "999")},
                    {"name": "Heavy tests (full suite)", "html_url": self.url},
                ]}
            return None

        with patch.dict(os.environ, self.environment, clear=True), patch.object(
            dispatcher.sys, "argv", ["dispatch_ci_triage.py", "Heavy tests (Linux)", "Heavy tests (full suite)"],
        ), patch.object(dispatcher, "api_request", side_effect=fake_api):
            dispatcher.main()

        self.assertEqual(len(calls), 2)
        self.assertIn("/actions/runs/123/jobs?per_page=100", calls[0][0])
        self.assertEqual(calls[0][1], "read-token")
        self.assertEqual(calls[1][1], "dispatch-token")
        self.assertEqual(calls[1][2], {
            "event_type": "ci-failure-triage",
            "client_payload": {
                "suite": "Heavy tests (Linux)",
                "job_url": self.url,
                "failure_kind": "tests",
                "message": f"Triage following failing test {self.url}",
            },
        })

    def test_rejects_unexpected_job_url_without_dispatching(self):
        with patch.dict(os.environ, self.environment, clear=True), patch.object(
            dispatcher.sys, "argv", ["dispatch_ci_triage.py", "Heavy tests (Linux)", "Heavy tests (full suite)"],
        ), patch.object(dispatcher, "api_request", return_value={"jobs": [
            {"name": "Heavy tests (full suite)", "html_url": "https://example.com/job/456"},
        ]}) as api:
            with self.assertRaisesRegex(ValueError, "unexpected job URL"):
                dispatcher.main()
        api.assert_called_once()

    def test_missing_dispatch_token_fails_before_api_call(self):
        environment = dict(self.environment)
        del environment["CI_TRIAGE_DISPATCH_TOKEN"]
        with patch.dict(os.environ, environment, clear=True), patch.object(
            dispatcher.sys, "argv", ["dispatch_ci_triage.py", "Heavy tests (Linux)", "Heavy tests (full suite)"],
        ), patch.object(dispatcher, "api_request") as api:
            with self.assertRaisesRegex(ValueError, "required"):
                dispatcher.main()
        api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
