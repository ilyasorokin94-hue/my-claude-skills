#!/bin/sh
# Test the dynamics operator preflight.
#
# Cloud Wordstat getDynamics: at weekly/monthly granularity, ONLY '+' operator is allowed.
# At daily granularity, all operators are allowed.

set -e

TESTS_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS_DIR="$(cd "$TESTS_DIR/.." && pwd)"
SKILL_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"

WORDSTAT_SCRIPT_DIR="$SCRIPTS_DIR"
WORDSTAT_SKILL_DIR="$SKILL_DIR"
export WORDSTAT_SCRIPT_DIR WORDSTAT_SKILL_DIR
# shellcheck disable=SC1091
. "$SCRIPTS_DIR/common.sh"

WORDSTAT_CLOUD_FOLDER_ID="b1g-test-folder"

# Run _xlate_request and capture both stdout and exit code.
# Returns "PASS" if exit 0, "FAIL:<msg>" if exit 2 (preflight reject).
preflight_check() {
    _method="$1"
    _params="$2"
    _err_file="${TMPDIR:-/tmp}/preflight_err_$$"
    if _xlate_request "$_method" "$_params" >/dev/null 2>"$_err_file"; then
        rm -f "$_err_file"
        echo "PASS"
    else
        _msg=$(cat "$_err_file")
        rm -f "$_err_file"
        echo "FAIL:$_msg"
    fi
}

assert_pass() {
    _name="$1"; _result="$2"
    case "$_result" in
        PASS) echo "  ok (pass): $_name" ;;
        *)    echo "  FAIL (expected pass): $_name → $_result"; exit 1 ;;
    esac
}

assert_fail() {
    _name="$1"; _result="$2"
    case "$_result" in
        FAIL:*PREFLIGHT_FAIL*) echo "  ok (fail): $_name" ;;
        *)                     echo "  FAIL (expected preflight fail): $_name → $_result"; exit 1 ;;
    esac
}

# --- Must PASS at weekly: intra-word hyphens, slashes, + operator ---
assert_pass "weekly + санкт-петербург" \
    "$(preflight_check dynamics '{"phrase":"санкт-петербург","period":"weekly","fromDate":"2025-01-01"}')"

assert_pass "weekly + б/у дымоход" \
    "$(preflight_check dynamics '{"phrase":"б/у дымоход","period":"weekly","fromDate":"2025-01-01"}')"

assert_pass "weekly + премиум-класс" \
    "$(preflight_check dynamics '{"phrase":"премиум-класс","period":"weekly","fromDate":"2025-01-01"}')"

assert_pass "weekly + юрист +по дтп (+ allowed)" \
    "$(preflight_check dynamics '{"phrase":"юрист +по дтп","period":"weekly","fromDate":"2025-01-01"}')"

assert_pass "monthly + plain phrase" \
    "$(preflight_check dynamics '{"phrase":"юрист дтп","period":"monthly","fromDate":"2025-01-01"}')"

# --- Must FAIL at weekly/monthly: token-leading -, !, " ( | ) ---
assert_fail "weekly + юрист -бесплатно (minus-word)" \
    "$(preflight_check dynamics '{"phrase":"юрист -бесплатно","period":"weekly","fromDate":"2025-01-01"}')"

assert_fail "weekly + \"юрист дтп\" (quotes)" \
    "$(preflight_check dynamics '{"phrase":"\"юрист дтп\"","period":"weekly","fromDate":"2025-01-01"}')"

assert_fail "weekly + (юрист|адвокат) (grouping)" \
    "$(preflight_check dynamics '{"phrase":"(юрист|адвокат) дтп","period":"weekly","fromDate":"2025-01-01"}')"

assert_fail "monthly + !юрист (exact form)" \
    "$(preflight_check dynamics '{"phrase":"!юрист","period":"monthly","fromDate":"2025-01-01"}')"

# --- Must PASS at daily: all operators allowed ---
assert_pass "daily + юрист -бесплатно" \
    "$(preflight_check dynamics '{"phrase":"юрист -бесплатно","period":"daily","fromDate":"2025-01-01"}')"

assert_pass "daily + \"юрист дтп\"" \
    "$(preflight_check dynamics '{"phrase":"\"юрист дтп\"","period":"daily","fromDate":"2025-01-01"}')"

assert_pass "daily + (a|b) грouping" \
    "$(preflight_check dynamics '{"phrase":"(a|b) test","period":"daily","fromDate":"2025-01-01"}')"

echo "test_dynamics_preflight: all passed"
