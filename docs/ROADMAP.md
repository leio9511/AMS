# AMS 2.0 Roadmap

## Current Phase
Phase 1.5: Backtest Reliability Hardening

## Current Goal
把 AMS 2.0 从“引擎可用”推进到“统一回测入口可直接使用，且具备可信验证闭环”。

## Phase Overview
- Phase 1: Backtest Foundation
- Phase 1.5: Backtest Reliability Hardening
- Phase 2: Live QMT Integration
- Phase 3: Production Research / Monitoring / Ops Hardening

## What’s Working
- Event-Driven core architecture is in place
- `HistoryDataFeed`, `CBRotationStrategy`, `SimBroker`, `BacktestRunner` are available
- CB double-low strategy can run with the correct code and data paths
- Historical CB dataset is standardized at:
  - `/root/projects/AMS/data/cb_history_factors.csv`

## Current Blockers
- `main_runner.py` unified CLI path is not truly executable yet
- Missing a real smoke test for the CLI main path
- Missing a validation framework (golden dataset / regression / walk-forward layering)

## Active Workstreams
1. Unified Backtest Entrypoint Bugfix
   - Fix parameter mapping in `main_runner.py`
   - Ensure real CLI execution works end-to-end
   - Add a real smoke test

2. Validation Framework
   - Define a golden dataset
   - Define golden outputs and checkpoints
   - Establish smoke / regression / walk-forward layers
   - Use this as a quality gate before Phase 2

## Gate to Next Phase
Before entering Phase 2, AMS must satisfy:
- `main_runner.py` can run real backtests directly
- Canonical code and data paths are fixed and documented
- Smoke test passes in CI/preflight
- `cb_rotation` has its first golden regression baseline
- Validation framework requirements are documented and tracked

## Next Actions
- Fix `main_runner.py` real CLI path
- Add a no-mock smoke test
- Drive ISSUE-1172
- Re-evaluate readiness for Phase 2

## Canonical Paths
- Code root: `/root/projects/AMS`
- Historical CB dataset: `/root/projects/AMS/data/cb_history_factors.csv`

## Linked Issues / PRDs
- ISSUE-1167: Standardized Unified Backtest Entrypoint
- ISSUE-1172: Validation Framework
- PRD: `docs/PRDs/PRD_Standardized_Unified_Backtest_Entrypoint.md`

## Notes
- `STATE.md` is runtime-oriented and may be overwritten by SDLC.
- This file is the human-facing program roadmap and status source of truth.
