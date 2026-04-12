#!/bin/bash
# ==========================================
# STANDARD AGENTIC PREFLIGHT SCRIPT TEMPLATE
# ==========================================
# Rule: Token-Optimized CI (Silent on Success, Verbose on Failure)
# Usage: Copy this to the root of any new project as `preflight.sh`
# and modify the "RUN_COMMAND" section for the specific tech stack.

PROJECT_DIR=$(dirname "$0")
LOG_FILE="$PROJECT_DIR/build_preflight.log"

echo "[$(date '+%H:%M:%S')] Starting Smart Preflight Checks..."

cd "$PROJECT_DIR" || exit 1
python3 -m py_compile scripts/adapter.py legacy_scripts/pilot_stock_radar.py tests/test_data_source.py > "$LOG_FILE" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "❌ PREFLIGHT FAILED (Exit Code: $EXIT_CODE)!"
    echo "=== ERROR DETAILS (Extracting relevant logs to save tokens) ==="
    grep -iE -A 10 -B 2 "error:|exception|failed|unresolved|expecting|traceback" "$LOG_FILE" | head -n 50
    echo "==============================================================="
    echo "Please fix the code above to pass the preflight gate."
    exit $EXIT_CODE
fi

# --- Contract Compliance Test ---
echo "[$(date '+%H:%M:%S')] Running Contract Compliance Test..."
pytest tests/test_data_source.py >> "$LOG_FILE" 2>&1
TEST_EXIT_CODE=$?

if [ $TEST_EXIT_CODE -ne 0 ]; then
    echo "❌ CONTRACT COMPLIANCE TEST FAILED (Exit Code: $TEST_EXIT_CODE)!"
    echo "=== ERROR DETAILS ==="
    cat "$LOG_FILE"
    echo "====================="
    exit $TEST_EXIT_CODE
fi

echo "✅ PREFLIGHT SUCCESS: Code compiled and all Unit/Probe tests passed."
rm -f "$LOG_FILE"
exit 0
