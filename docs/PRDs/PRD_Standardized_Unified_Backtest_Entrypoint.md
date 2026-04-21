---
Affected_Projects: [AMS]
Related_Issue: ISSUE-1167
---

# PRD: Standardized Unified Backtest Entrypoint (main_runner.py 2.0)

## 1. Context & Problem
AMS 2.0 requires a formal, industrial-grade CLI. Ad-hoc scripting has caused data drift and precision loss. We need an "Agent-First" entry point that guarantees bit-level accuracy across the entire lifecycle, from parameter injection to final JSON reporting.

## 2. Requirements & User Stories
1.  **US 1 (Unified CLI)**: Refactor `main_runner.py` into a fully parameterized CLI.
2.  **US 2 (Self-Documenting Help)**: Provide hardcoded help strings for all 11 parameters to guide Agent discovery.
3.  **US 3 (Strategy Factory)**: Implement a Registry pattern in `ams.core.factory` for type-safe strategy loading.
4.  **US 4 (Bit-Accurate Dual-Reporting)**:
    - **Human Mode (Default)**: ASCII table.
    - **Agent Mode (`--format json`)**: Structured output that PRESERVES `Decimal` precision using exact string serialization.

## 3. Architecture & Technical Strategy
*   **CLI Infrastructure**: Python `argparse`.
*   **Strategy Registry**: New module `ams.core.factory.py` for decoupled instantiation.
*   **High-Precision Reporting**: 
    - New module `ams/utils/reporting.py`.
    - **Anti-Loss Policy**: Use a custom `DecimalEncoder` that inherits `json.JSONEncoder` to serialize all `Decimal` values as high-precision strings.
*   **Rollback Strategy**:
    - **Baseline**: `873ca9e`.
    - **Recovery**: `git reset --hard 873ca9e && git clean -fd`.

## 4. Acceptance Criteria
*   **AC 1 (CLI Determinism)**: `python3 main_runner.py --help` output must match Section 7.1 exactly.
*   **AC 2 (Machine Parsability)**: When run with `--format json`, all financial fields must be represented as strings (e.g., `"123.4567"`) and match the internal `Decimal` values character-for-character.
*   **AC 3 (Validation Safety)**: Invalid parameters must trigger a `ValueError` with the specific message defined in Section 7.4.

## 5. Overall Test Strategy & Quality Goal
*   **Precision Round-trip Test**: Verify that parsing JSON output back into `Decimal` yields values identical to the pre-serialization state.
*   **Regression**: Bit-identical ASCII report output for the verified 2025 "Golden Set".

## 6. Framework Modifications
- `/root/projects/AMS/main_runner.py`
- `/root/projects/AMS/ams/core/factory.py`
- `/root/projects/AMS/ams/utils/reporting.py`
- `/root/projects/AMS/SKILL.md`

## 7. Hardcoded Content (Anti-Hallucination)

### 7.1 Complete CLI Argument Specification:
```text
--strategy: The identifier of the strategy to run (supported: 'cb_rotation').
--start-date: Backtest start date in YYYY-MM-DD format.
--end-date: Backtest end date in YYYY-MM-DD format.
--capital: Initial trading capital (e.g., 4000000.0).
--top-n: Number of top-ranked securities to hold.
--rebalance: Rebalancing frequency ('daily' or 'weekly').
--tp-mode: Take-profit mode ('position', 'intraday', or 'both').
--tp-pos: Threshold for cost-basis take-profit (e.g., 0.20).
--tp-intra: Threshold for intraday momentum take-profit (e.g., 0.08).
--sl: Threshold for intraday stop-loss (e.g., -0.08).
--format: Output format ('text' or 'json'). Default: 'text'.
```

### 7.2 Mandatory JSON Output Keys (Schema):
```json
{
  "summary": {
    "total_return": "STR_DECIMAL",
    "max_drawdown": "STR_DECIMAL",
    "calmar_ratio": "STR_DECIMAL",
    "final_equity": "STR_DECIMAL"
  },
  "weekly_performance": [
    {
      "week_ending": "YYYY-MM-DD",
      "total_assets": "STR_DECIMAL",
      "weekly_profit_pct": "STR_DECIMAL",
      "cumulative_pct": "STR_DECIMAL"
    }
  ]
}
```

### 7.3 Skill Documentation Injection:
```markdown
5. **Strategy Backtester**:
   `python3 main_runner.py --strategy <ID> --start-date <YYYY-MM-DD> --end-date <YYYY-MM-DD> --capital <FLOAT> --top-n <INT> --rebalance <daily|weekly> --tp-mode <both|position|intraday> --tp-pos <FLOAT> --tp-intra <FLOAT> --sl <FLOAT> [--format json]`
   Use this for rigorous strategy validation. Use `--format json` for bit-accurate results.
```

### 7.4 Mandatory Exception Messages:
```text
ValueError: "ERROR: Strategy '{strategy_id}' not found in registry."
ValueError: "ERROR: --tp-mode '{tp_mode}' requires both --tp-pos and --tp-intra to be set."
```
