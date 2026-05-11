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
- Historical CB dataset is managed as explicit, configuration-controlled mutable research data.

## Current Blockers
- `main_runner.py` unified CLI path is not truly executable yet
- Missing a real smoke test for the CLI main path
- Missing a validation framework (golden dataset / regression / walk-forward layering)
- ISSUE-1142 governance hardening still depends on the repaired CB source-contract layer remaining explicit, observable, and regression-protected

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

3. CB Source-Contract Hardening & Redemption Observability
   - Keep `underlying_ticker` and `premium_rate` on explicit documented source contracts
   - **Redemption Wave 1**: Contract split applied (`redeem_risk` vs `is_redeemed`). See ISSUE-13.
   - **Redemption Wave 2**: Align observability & validation (metrics and audit report properly distinguish risk-state from terminal-state). Phase 1.5 observability semantic split is a prerequisite to real event-driven state (Wave 3). See ISSUE-15.
   - **Redemption Wave 3** *(Pending)*: Integrate event ledger / shared-state for true announcement-driven `redeem_risk` hydration.
   - Treat this as prerequisite upstream input quality for ISSUE-1142 dataset governance

## Gate to Next Phase
Before entering Phase 2, AMS must satisfy:
- `main_runner.py` can run real backtests directly
- Canonical code and data paths are fixed and documented
- Smoke test passes in CI/preflight
- `cb_rotation` has its first golden regression baseline
- Validation framework requirements are documented and tracked
- Redemption observability (Wave 2) is complete, preventing misleading terminal-count proxies
- ISSUE-1142 is a blocking issue for AMS Phase 2. AMS must not enter Live QMT Integration until the historical CB dataset is strictly managed as explicit, configuration-controlled mutable research data, and the semantic quality gates defined in this PRD are enforced without declaring a root-only machine path as the canonical contract.

## Next Actions
- Fix `main_runner.py` real CLI path
- Add a no-mock smoke test
- Drive ISSUE-1172
- Re-evaluate readiness for Phase 2

## Path Contracts (Phase 1A Vocabulary)
- **Repo-owned stable assets**: Must use repo-relative paths (deployment-independent).
- **Mutable research/backtest data**: Explicit and configuration-controlled (resolved via CLI > ENV > AMS-owned config > project-local default).
- **Runtime outputs/state**: Deployment-relative, overrideable, and do not require OpenClaw workspace.

## Linked Issues / PRDs
- ISSUE-13: Redemption Wave 1 - Contract Split (`redeem_risk` vs `is_redeemed`)
- ISSUE-15: Redemption Wave 2 - Observability / Validation Alignment (Phase 1.5 Semantic Split)
- ISSUE-1167: Standardized Unified Backtest Entrypoint
- ISSUE-1172: Validation Framework
- ISSUE-1182: CB source-contract repair for `underlying_ticker`, `premium_rate`, and `is_redeemed`
- ISSUE-1142: CB research dataset governance and quality gates
- PRD: `docs/PRDs/PRD_Standardized_Unified_Backtest_Entrypoint.md`
- PRD: `docs/PRDs/PRD_CB_Source_Contract_Repair_for_Premium_Underlying_and_Redemption.md`
- PRD: `docs/PRDs/PRD_Wave_2_Redeem_Risk_Observability_Alignment.md`

## Notes
- `STATE.md` is runtime-oriented and may be overwritten by SDLC.
- This file is the human-facing program roadmap and status source of truth.
