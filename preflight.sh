#!/bin/bash
# ==========================================
# STANDARD AGENTIC PREFLIGHT SCRIPT TEMPLATE
# ==========================================
# Rule: Token-Optimized CI (Silent on Success, Verbose on Failure)

set -uo pipefail

PROJECT_DIR=$(dirname "$0")
LOG_FILE="$PROJECT_DIR/build_preflight.log"
IGNORE_MANIFEST_PATH="$PROJECT_DIR/ignore_tests.json"
IGNORE_HELPER_PATH="$PROJECT_DIR/scripts/preflight_ignore_manifest.py"
PYTEST_IGNORE_OUTPUT_FILE=$(mktemp)
PYTEST_IGNORE_ARGS=()
MODE="fail-fast"

cleanup_temp_files() {
    rm -f "$PYTEST_IGNORE_OUTPUT_FILE"
}

print_failure_details() {
    local exit_code="$1"

    echo "❌ PREFLIGHT FAILED (Exit Code: $exit_code)!"
    echo "=== ERROR DETAILS (Extracting relevant logs to save tokens) ==="
    if grep -iE -A 10 -B 2 "error:|exception|failed|unresolved|expecting|traceback|❌" "$LOG_FILE" | head -n 50; then
        :
    else
        tail -n 50 "$LOG_FILE"
    fi
    echo "==============================================================="
    echo "Please fix the code above to pass the preflight gate."
}

parse_args() {
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --report-all)
                MODE="report-all"
                ;;
            *)
                echo "Unknown preflight mode flag: $1" >> "$LOG_FILE"
                return 2
                ;;
        esac
        shift
    done
}

extract_pytest_summary_lines() {
    awk '
        /^=+ short test summary info =+$/ { in_summary=1; next }
        in_summary && /^=+/ { exit }
        in_summary && /^(FAILED|ERROR) / { print }
    ' "$LOG_FILE"
}

print_report_all_summary() {
    local exit_code="$1"
    local -a summary_lines=()

    mapfile -t summary_lines < <(extract_pytest_summary_lines)
    if [ ${#summary_lines[@]} -eq 0 ]; then
        mapfile -t summary_lines < <(grep -E '^(FAILED|ERROR) ' "$LOG_FILE" || true)
    fi

    echo "=== REPORT-ALL SUMMARY ==="
    echo "MODE: report-all"
    echo "PYTEST RESULT: failed (exit code: $exit_code)"
    echo "FAILED TESTS:"
    if [ ${#summary_lines[@]} -eq 0 ]; then
        echo "(no failed test entries captured)"
    else
        local line
        local entry
        for line in "${summary_lines[@]}"; do
            entry="${line#FAILED }"
            entry="${entry#ERROR }"
            entry="${entry%% - *}"
            echo "$entry"
        done
    fi
    echo "SHORT SUMMARY INFO:"
    if [ ${#summary_lines[@]} -eq 0 ]; then
        echo "(no short summary info captured)"
    else
        printf '%s\n' "${summary_lines[@]}"
    fi
    echo "=== END REPORT-ALL SUMMARY ==="
}

# JSON parsing and manifest validation belong entirely to the Python helper.
# The shell entrypoint only blocks or permits pytest based on helper success,
# and consumes the newline-delimited --ignore arguments emitted by that helper.
run_contract_compliance_test() {
    echo "[$(date '+%H:%M:%S')] Running Contract Compliance Test..."

    python3 "$IGNORE_HELPER_PATH" --manifest "$IGNORE_MANIFEST_PATH" --repo-root "$PROJECT_DIR" > "$PYTEST_IGNORE_OUTPUT_FILE" 2>> "$LOG_FILE"
    local helper_exit_code=$?
    if [ $helper_exit_code -ne 0 ]; then
        return $helper_exit_code
    fi

    PYTEST_IGNORE_ARGS=()
    if [ -s "$PYTEST_IGNORE_OUTPUT_FILE" ]; then
        mapfile -t PYTEST_IGNORE_ARGS < "$PYTEST_IGNORE_OUTPUT_FILE"
    fi

    return 0
}

trap cleanup_temp_files EXIT
: > "$LOG_FILE"

parse_args "$@"
EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    print_failure_details "$EXIT_CODE"
    exit $EXIT_CODE
fi

echo "[$(date '+%H:%M:%S')] Starting Smart Preflight Checks..."

cd "$PROJECT_DIR" || exit 1

# --- Global Syntax Check ---
find . -name "*.py" -not -path "*/\.*" -not -path "*/__pycache__/*" -not -path "*/docs/*" -print0 | xargs -0 python3 -m py_compile > "$LOG_FILE" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    print_failure_details "$EXIT_CODE"
    exit $EXIT_CODE
fi

# --- Contract Compliance Test ---
run_contract_compliance_test
EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    print_failure_details "$EXIT_CODE"
    exit $EXIT_CODE
fi

pytest "${PYTEST_IGNORE_ARGS[@]}" >> "$LOG_FILE" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    print_failure_details "$EXIT_CODE"
    if [ "$MODE" = "report-all" ]; then
        print_report_all_summary "$EXIT_CODE"
    fi
    exit $EXIT_CODE
fi

TOTAL_PASSED=$(grep -oE '[0-9]+ passed' "$LOG_FILE" | awk '{print $1}' | head -n 1)
if [ -z "$TOTAL_PASSED" ]; then
    TOTAL_PASSED="0"
fi

echo "✅ PREFLIGHT SUCCESS: Code compiled and $TOTAL_PASSED tests passed."
rm -f "$LOG_FILE"
exit 0
