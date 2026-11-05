#!/bin/sh
# Test runner for wordstat skill — POSIX sh, no network.

set -e

TESTS_DIR="$(cd "$(dirname "$0")" && pwd)"

PASS=0
FAIL=0
FAILED_TESTS=""

for t in "$TESTS_DIR"/test_*.sh; do
    [ -f "$t" ] || continue
    name=$(basename "$t" .sh)
    printf '%s ... ' "$name"
    if sh "$t" >/dev/null 2>&1; then
        printf 'PASS\n'
        PASS=$((PASS + 1))
    else
        printf 'FAIL\n'
        FAIL=$((FAIL + 1))
        FAILED_TESTS="$FAILED_TESTS $name"
        # Re-run with output for diagnosis
        echo "--- output of $name ---"
        sh "$t" 2>&1 || true
        echo "--- end ---"
    fi
done

echo ""
echo "Results: $PASS passed, $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
    echo "Failed: $FAILED_TESTS"
    exit 1
fi
exit 0
