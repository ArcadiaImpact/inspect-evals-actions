#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path
import argparse

REPORT_THRESHOLD = float(os.environ.get('SLOW_TEST_REPORT_THRESHOLD', 10.0))
FAIL_THRESHOLD = float(os.environ.get('SLOW_TEST_FAIL_THRESHOLD', 60.0))


def lint_test_report_file(report_file: Path) -> dict:
    """Return dict of slow tests in this report: nodeid -> duration"""
    if not report_file.exists():
        print(f'Warning: {report_file} not found, skipping')
        return {}

    slow_tests: dict = {}
    with open(report_file) as f:
        for line in f:
            try:
                obj = json.loads(line)
            except Exception:
                continue

            if obj.get('$report_type') != 'TestReport':
                continue
            if obj.get('when') != 'call':
                continue
            if obj.get('outcome') == 'skipped':
                continue
            if 'huggingface' in obj.get('keywords', {}):
                continue

            dur = float(obj.get('duration') or 0.0)
            nodeid = obj.get('nodeid', '<unknown>')

            if dur >= REPORT_THRESHOLD:
                # Keep the slowest duration if duplicates exist
                if nodeid not in slow_tests or dur > slow_tests[nodeid]:
                    slow_tests[nodeid] = dur
    return slow_tests


def lint_slow_tests(reports_dir: Path) -> None:
    all_slow_tests: dict = {}

    for report_file in Path(reports_dir).glob("*.jsonl"):
        report_slow = lint_test_report_file(report_file)
        for nodeid, dur in report_slow.items():
            # Keep the slowest duration across reports
            if nodeid not in all_slow_tests or dur > all_slow_tests[nodeid]:
                all_slow_tests[nodeid] = dur

    if not all_slow_tests:
        print(f'All tests under {REPORT_THRESHOLD}s or properly marked with @pytest.mark.slow')
        return

    # Sort by duration descending
    sorted_tests = sorted(all_slow_tests.items(), key=lambda x: x[1], reverse=True)
    failures = [(dur, nodeid) for nodeid, dur in sorted_tests if dur >= FAIL_THRESHOLD]

    header = '=' * 80 if failures else '-' * 80
    print(header)
    for nodeid, dur in sorted_tests:
        marker = ' [FAIL]' if dur >= FAIL_THRESHOLD else ''
        print(f'{dur:6.2f}s  {nodeid}{marker}')

    if failures:
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check pytest reports for unmarked slow tests.")
    parser.add_argument(
        "--reports-dir",
        type=Path,
        required=True,
        help="Directory containing pytest JSONL report files"
    )
    args = parser.parse_args()
    lint_slow_tests(args.reports_dir)
