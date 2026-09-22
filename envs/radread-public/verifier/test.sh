#!/bin/bash
# verifier/test.sh: run the checks, write reward.txt / reward.json / ctrf.json.
# The reward is graded: the fraction of tasks passed.
set -eu
VERIFIER_DIR="$(cd "$(dirname "$0")" && pwd)"
LOGS_DIR="${LOGS_DIR:-/logs/verifier}"
# An optional workspace argument overrides RADREAD_WORKSPACE. Relative paths are
# interpreted from the caller's directory, including RADREAD_GOLD and LOGS_DIR.
if [ "$#" -gt 1 ]; then
  echo "usage: $0 [workspace]" >&2
  exit 2
fi
export RADREAD_WORKSPACE="${1:-${RADREAD_WORKSPACE:-/root}}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
mkdir -p "$LOGS_DIR"
status=0
python3 -m pytest "$VERIFIER_DIR/test_outputs.py" --junitxml="$TMP_DIR/junit.xml" -q -p no:cacheprovider \
  > "$TMP_DIR/pytest.log" 2>&1 || status=$?
if [ "$status" -ne 0 ] && [ "$status" -ne 1 ]; then
  cat "$TMP_DIR/pytest.log" >&2
  exit "$status"
fi
python3 - "$LOGS_DIR" "$TMP_DIR/junit.xml" <<'EOF'
import json
import sys
import xml.etree.ElementTree as ET
logs = sys.argv[1]
root = ET.parse(sys.argv[2]).getroot()
suite = root.find('testsuite') if root.tag == 'testsuites' else root
cases = [c for c in suite.iter('testcase') if c.get('classname', '').endswith('TestTask')]
total = len(cases)
if not total or any(True for _ in suite.iter('error')):
    raise RuntimeError('verifier could not grade tasks; no reward was produced')
failed = sum(1 for c in cases if c.find('failure') is not None or c.find('error') is not None)
passed = total - failed
reward = passed / total
with open(f'{logs}/reward.txt', 'w') as f:
    f.write(f'{reward:.6f}\n')
with open(f'{logs}/reward.json', 'w') as f:
    json.dump({'reward': reward}, f)
results = []
for case in cases:
    status = 'failed' if (case.find('failure') is not None or case.find('error') is not None) else 'passed'
    message = ''
    node = case.find('failure')
    if node is None:
        node = case.find('error')
    if node is not None:
        message = (node.get('message') or '')[:500]
    results.append({'name': f"{case.get('classname', '')}::{case.get('name', '')}",
                    'status': status, 'message': message})
with open(f'{logs}/ctrf.json', 'w') as f:
    json.dump({'reportName': 'radread-verifier', 'summary': {'total': total, 'passed': passed,
               'failed': failed}, 'results': results}, f, indent=1)
print(f'reward {reward:.4f} ({passed}/{total})')
EOF
