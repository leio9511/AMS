# PR-004: Fix Argparse and Logic Routing in etf_tracker.py

## Goal
Correct the critical bug from PR_003 where `argparse` was not implemented, causing the script to ignore `--mode` arguments. This PR will enforce strict logic routing based on the provided mode.

## Scope
- `scripts/etf_tracker.py`
- `preflight.sh`

## Contracts
- The script MUST use Python's `argparse` library to handle `--mode` (`morning`, `monitor`, `closing`).
- The script's `main()` function must have clear `if/elif/else` blocks that route execution based on the parsed mode.

## Acceptance Criteria (AC)
1. Running `python3 scripts/etf_tracker.py --mode=morning` ONLY executes the morning report logic.
2. Running `python3 scripts/etf_tracker.py --mode=monitor` ONLY executes the intraday anomaly scan.
3. Running `python3 scripts/etf_tracker.py --mode=closing` ONLY executes the closing report logic (including Low-PE).
4. `preflight.sh` is updated to include a "Contract Compliance Test":
   - It MUST run `python3 scripts/etf_tracker.py --mode=morning --dry-run` (or similar dummy flag) and check for a successful exit code to physically prove `argparse` is working.

## Anti-Patterns
- **DO NOT** write a single monolithic `main()` function. Use helper functions for each mode to keep the logic clean.
- **DO NOT** "cheat" on the preflight test. The test must physically invoke the script with a command-line argument.
