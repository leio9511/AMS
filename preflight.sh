#!/bin/bash
# ==========================================
# STANDARD AGENTIC PREFLIGHT SCRIPT TEMPLATE
# ==========================================
# Rule: Token-Optimized CI (Silent on Success, Verbose on Failure)

PROJECT_DIR=$(dirname "$0")
LOG_FILE="$PROJECT_DIR/build_preflight.log"
IGNORE_MANIFEST_PATH="$PROJECT_DIR/ignore_tests.json"
IGNORE_HELPER_PATH="$PROJECT_DIR/scripts/preflight_ignore_manifest.py"

echo "[$(date '+%H:%M:%S')] Starting Smart Preflight Checks..."

cd "$PROJECT_DIR" || exit 1

# --- Global Syntax Check ---
find . -name "*.py" -not -path "*/\.*" -not -path "*/__pycache__/*" -not -path "*/docs/*" -print0 | xargs -0 python3 -m py_compile > "$LOG_FILE" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "❌ PREFLIGHT FAILED (Exit Code: $EXIT_CODE)!"
    echo "=== ERROR DETAILS (Extracting relevant logs to save tokens) ==="
    if grep -iE -A 10 -B 2 "error:|exception|failed|unresolved|expecting|traceback|❌" "$LOG_FILE" | head -n 50; then
        :
    else
        tail -n 50 "$LOG_FILE"
    fi
    echo "==============================================================="
    echo "Please fix the code above to pass the preflight gate."
    exit $EXIT_CODE
fi

# --- Contract Compliance Test ---
echo "[$(date '+%H:%M:%S')] Running Contract Compliance Test..."
PYTEST_IGNORE_OUTPUT=$(python3 "$IGNORE_HELPER_PATH" --manifest "$IGNORE_MANIFEST_PATH" --repo-root "$PROJECT_DIR" 2>> "$LOG_FILE")
EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo "❌ PREFLIGHT FAILED (Exit Code: $EXIT_CODE)!"
    echo "=== ERROR DETAILS (Extracting relevant logs to save tokens) ==="
    if grep -iE -A 10 -B 2 "error:|exception|failed|unresolved|expecting|traceback|❌" "$LOG_FILE" | head -n 50; then
        :
    else
        tail -n 50 "$LOG_FILE"
    fi
    echo "==============================================================="
    echo "Please fix the code above to pass the preflight gate."
    exit $EXIT_CODE
fi
PYTEST_IGNORE_ARGS=()
if [ -n "$PYTEST_IGNORE_OUTPUT" ]; then
    mapfile -t PYTEST_IGNORE_ARGS <<< "$PYTEST_IGNORE_OUTPUT"
fi
pytest "${PYTEST_IGNORE_ARGS[@]}" >> "$LOG_FILE" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "❌ PREFLIGHT FAILED (Exit Code: $EXIT_CODE)!"
    echo "=== ERROR DETAILS (Extracting relevant logs to save tokens) ==="
    if grep -iE -A 10 -B 2 "error:|exception|failed|unresolved|expecting|traceback|❌" "$LOG_FILE" | head -n 50; then
        :
    else
        tail -n 50 "$LOG_FILE"
    fi
    echo "==============================================================="
    echo "Please fix the code above to pass the preflight gate."
    exit $EXIT_CODE
fi

TOTAL_PASSED=$(grep -oE '[0-9]+ passed' "$LOG_FILE" | awk '{print $1}' | head -n 1)
if [ -z "$TOTAL_PASSED" ]; then
    TOTAL_PASSED="0"
fi

echo "✅ PREFLIGHT SUCCESS: Code compiled and $TOTAL_PASSED tests passed."
rm -f "$LOG_FILE"
exit 0
