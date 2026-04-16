# AMS Project State

## Active Epic: AMS v2.0 Event-Driven Architecture Refactoring (ISSUE-1133)
**Goal:** Migrate from static procedural scripts to a highly cohesive, loosely coupled Event-Driven Architecture (EDA) using the Strangler Fig Pattern to ensure identical execution logic across backtesting, paper trading, and live execution without disrupting existing operations.

### Phase 1 Roadmap (Backtest Implementation)
- [x] **Architecture Base**: Implement Base classes (`BaseStrategy`, `BaseDataFeed`, `BaseBroker`) and `BacktestRunner` (Completed via SDLC PR-001, PR-002, PR-003).
- [x] **PRD 1 (ISSUE-1134)**: HistoryDataFeed Implementation for CB Backtesting.
- [x] **PRD 2 (ISSUE-1135)**: Base Double-Low Strategy & Backtest Loop (Solves baseline for ISSUE-1131).
- [x] **PRD 3 (ISSUE-1136)**: Risk Control Implementation (Force Redemption, ST, -8% Stop-Loss. Solves ISSUE-1127).

### Phase 2 Roadmap (Live QMT 接管 - Pending)
- [ ] Implement `QMTBroker` and `LiveRunner`.
- [ ] Wire Windows Webhook trigger to OpenClaw.

## Active PRs
None currently. Ready to begin Phase 1 (ISSUE-1102).
