# AMS Project State

## Active Epic: AMS v2.0 Event-Driven Architecture Refactoring (ISSUE-1101)
**Goal:** Migrate from static procedural scripts to a highly cohesive, loosely coupled Event-Driven Architecture (EDA) to support pluggable strategies (ETF, CB, Stock Picking).

### Roadmap & Milestone Tickets
- [ ] **Phase 1: ISSUE-1102** - Core Engine & Legacy Archive (Implement EventEngine, Gateway, and restructure directories)
- [ ] **Phase 2: ISSUE-1103** - Pre-market Financial ETL on Windows (Batch local .DAT files into a lightweight JSON factor dictionary)
- [ ] **Phase 3: ISSUE-1104** - Strategy Migration & Sandbox (Refactor ETF/CB/Crystal Fly into standard event-driven classes)
- [ ] **Phase 4: ISSUE-1105** - CI/CD Topology & Agent Integration (Automated push to Windows, OpenClaw HEARTBEAT hooks)

## Active PRs
None currently. Ready to begin Phase 1 (ISSUE-1102).
