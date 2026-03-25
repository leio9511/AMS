# PR-002: Convert AMS to Stateless OpenClaw Native Capability

## Goal
Tear down the detached daemon architecture. Strip the `while True` loop and time-based `if` statements from `etf_tracker.py` to make it a pure, stateless CLI tool. The tool must execute specific reports based on command-line arguments and integrate perfectly with OpenClaw Cron scheduling.

## Scope
- `etf_tracker.py` (rename/refactor to `ams_stateless.py` or modify in place)
- Remove all `time.sleep()`, `while running:`, and internal `datetime` checks that dictate *when* to run.

## Contracts
- The script must use `argparse` to accept a `--mode` argument with the following values:
  1. `morning`: Executes the pre-market/opening report (CB discount scan + opening index levels).
  2. `monitor`: Executes the intraday anomaly scan. If no anomalies exist, **exit silently (0) without sending a Telegram message.**
  3. `closing`: Executes the post-market summary, WHICH MUST INCLUDE the low-PE screener (水晶苍蝇拍).
- The script must check if today is a trading day (`is_trading_day()`). If it is a weekend or holiday, the script must exit immediately (Code 0) without sending any messages.
- The script must use `openclaw message send` or the HTTP equivalent to deliver Telegram messages.

## Acceptance Criteria (AC)
1. Running `python3 etf_tracker.py --mode=morning` on a non-trading day produces no Telegram output.
2. Running `python3 etf_tracker.py --mode=closing` on a trading day successfully delivers the closing report containing the low-PE screener data.
3. The script terminates completely (returns to the bash prompt) in under 30 seconds for any mode.
4. `./preflight.sh` runs successfully.

## Anti-Patterns (尸检报告/避坑指南)
- **DO NOT** use `while True` or `time.sleep()` to wait for the next market event. The script must execute its mode and exit.
- **DO NOT** hardcode time checks like `if "09:25" <= current_time <= "09:45"`. OpenClaw Cron will handle executing the script at exactly 09:25. The script only needs to trust that it was called at the right time.
- **DO NOT** send "All clear" or "No anomalies" messages in `--mode=monitor`. It must be completely silent unless a threshold is breached to avoid spamming the Boss.
