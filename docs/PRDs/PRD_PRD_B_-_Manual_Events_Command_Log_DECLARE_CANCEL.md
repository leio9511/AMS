---
Affected_Projects: [AMS]
Context_Workdir: /home/openclaw/projects/AMS
---

# PRD: PRD B - Manual Events Command Log (DECLARE CANCEL)

## 1. Context & Problem (业务背景与核心痛点)

EPIC: #13
Depends on: PRD A / issue #17 delivered the TuShare full-snapshot fetch + orchestration path.

AMS redemption pipeline already has a Wave 3 ledger-based ingestion and derivation model:
- upstream facts are normalized into Import CSV rows
- persisted ledger is the only post-ingestion truth source
- canonical artifacts are derived from persisted ledger revisions

The missing capability is a **safe degraded-mode manual input path** for the operational case where TuShare is temporarily unavailable during normal daily runs.

This PRD must stay narrowly scoped. The goal is **not** to redesign Wave 3 identity semantics or unify manual and TuShare into a single business-event stream. That larger problem exists, but it is not approved inside PRD B.

### Frozen design baseline for this PRD

1. **Wave 3 event identity contract is frozen in this PRD.**
   This PRD does **not** change existing `event_id` / identity semantics.

2. **TuShare remains the primary authoritative upstream source for normal operation.**
   This PRD addresses temporary source unavailability, not semantic correction of trusted TuShare content.

3. **Manual input is a degraded-mode operational fallback.**
   It is not a general source-convergence mechanism and not a long-term replacement for TuShare.

4. **Bootstrap cannot be replaced by manual input.**
   If the system lacks the required baseline and TuShare is unavailable, the pipeline must fail.

5. **This PRD does not solve cross-source lifecycle convergence.**
   Topics such as manual-to-TuShare takeover, unified event stream semantics, or identity migration are explicitly deferred.

### The actual problem PRD B must solve

Operators currently lack an auditable, append-only way to inject temporary manual redemption events when TuShare fetch fails on a routine run.

PRD B therefore needs to provide:
- an append-only command log
- a small CLI for adding commands
- deterministic reduction from command history to current manual facts
- a bounded degraded-mode ingestion path in the existing pipeline
- clear non-goals so downstream implementation does not silently mutate Wave 3 architecture

## 2. Requirements & User Stories (需求定义)

### Functional Requirements

- **FR1 — Append-only manual command log**
  Add `data/manual_events.csv` as the truth source for manual operator commands. Existing rows are never edited or deleted.

- **FR2 — CLI appends commands only**
  `scripts/manual_redemption_inject.py` appends `DECLARE` or `CANCEL` rows to `manual_events.csv` and performs basic argument validation.

- **FR3 — Deterministic reduce of manual command history**
  A pure transform reduces the append-only command history by `source_native_event_id` into the latest manual state for each identity.

- **FR4 — Bounded degraded-mode ingestion**
  During non-bootstrap daily runs, if TuShare fetch fails and reduced manual facts are non-empty, the pipeline may continue in a clearly marked degraded mode.

- **FR5 — No Wave 3 identity-contract changes**
  This PRD must not change existing ledger identity rules, existing `event_id` construction, or re-define source as a revision-only attribute.

- **FR6 — No cross-source convergence logic**
  This PRD must not implement manual/TuShare unified-stream lifecycle semantics such as automatic takeover, supersede, or cross-source conflict retirement.

- **FR7 — Auditability**
  Manual command history must remain git-tracked and human-readable so operators can inspect who added what and why.

### Non-Functional Requirements

- **NFR1 — Purity of reducer**
  Manual reduction logic must be deterministic and testable without ledger reads, file writes, or runtime clock access.

- **NFR2 — Minimal surface-area change**
  Keep the implementation limited to the manual input path and the smallest orchestration additions needed for degraded mode.

- **NFR3 — Explicit degraded status**
  Downstream artifacts and operator-visible freshness state must clearly indicate degraded/manual mode rather than pretending to be a normal successful TuShare sync.

### User Stories

- As an operator, when TuShare is temporarily unavailable on a normal run, I want to record a manual redemption event through a simple CLI so the day’s pipeline can still proceed in a controlled degraded mode.
- As an operator, if I entered a manual event by mistake, I want to append a cancellation command without rewriting history.
- As an auditor, I want the full manual command history preserved in git so I can trace operational decisions.
- As a downstream engineer, I need PRD B to stay within its approved boundary and not silently alter Wave 3 identity architecture.

### Explicit Non-Goals

This PRD does **not**:
- change Wave 3 `event_id` / identity contract
- redefine `event_id = source_native_event_id`
- merge manual and TuShare into one shared business-event stream
- implement automatic manual → TuShare takeover or `SUPERSEDED` lifecycle
- implement manual override of active TuShare facts
- solve general source-conflict resolution
- use canonical artifacts to back-propagate new source-of-truth logic beyond the minimal degraded-mode orchestration needed here

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 New files

| File | Purpose |
|---|---|
| `data/manual_events.csv` | Append-only operator command log |
| `scripts/manual_redemption_inject.py` | CLI for appending DECLARE/CANCEL commands |
| `etl/manual_event_injector.py` | Pure reduction/transform logic from command log to manual ingress facts |

### 3.2 Modified files

| File | Change |
|---|---|
| `etl/redemption_fetcher.py` | Read manual command log, invoke reducer, and enable bounded degraded-mode orchestration |
| `etl/tushare_provider.py` | Minimal import-path adjustment only if required to accept manual ingress rows through the already-approved ingestion surface |
|

If implementation later appears to require deep changes in `etl/redemption_ledger.py` identity semantics, that is out of scope and must trigger a new PRD discussion rather than being implemented under PRD B.

### 3.3 Core design principle: keep PRD B narrow

PRD B is intentionally **not** a ledger-identity migration.

Therefore:
- keep the current Wave 3 identity contract unchanged
- treat manual input as a bounded fallback source for degraded operations
- limit transformation responsibility to producing valid manual ingress facts
- do not add new cross-source lifecycle semantics in the ledger layer

### 3.4 `manual_events.csv` schema

`manual_events.csv` is append-only and git-tracked.

Schema:

```text
command,source_native_event_id,bond_code,announcement_date,delisting_date,reason,created_at
```

Rules:
- `command` is `DECLARE` or `CANCEL`
- `source_native_event_id` is provided by the operator and is the identity key for reducing manual commands
- `delisting_date` is required for `DECLARE`
- `delisting_date` must be empty for `CANCEL`
- `reason` is required for both commands
- `created_at` is written by the CLI at append time

Example:

```csv
DECLARE,123456.SH_2026-05-15,123456.SH,2026-05-15,2026-06-20,TuShare API unavailable,2026-05-15T10:00:00Z
CANCEL,123456.SH_2026-05-15,123456.SH,2026-05-15,,wrong manual entry,2026-05-15T11:00:00Z
```

### 3.5 CLI contract

`manual_redemption_inject.py` is a thin append-only writer.

Responsibilities:
- validate required arguments
- normalize command casing
- enforce `DECLARE` vs `CANCEL` field rules
- append exactly one CSV row
- never rewrite prior rows

Non-responsibilities:
- no ledger reads
- no source-convergence logic
- no takeover logic
- no canonical regeneration logic

### 3.6 Reduction model

`etl/manual_event_injector.py` reduces command history per `source_native_event_id`.

Reducer semantics:
- latest effective `DECLARE` => emit one active manual fact
- latest effective `CANCEL` => emit no manual fact for that identity
- `DECLARE -> CANCEL -> DECLARE` => final DECLARE wins
- `CANCEL` with no preceding DECLARE in command history => reduced output is empty for that identity

This reducer is intentionally **command-log local**.
It does not inspect ledger history and does not attempt to encode post-ingestion lifecycle.

### 3.7 Output of manual reducer

The reducer outputs a DataFrame matching the existing ingestion surface used for redemption facts, with `source="manual"` populated for rows originating from the reduced manual state.

Important boundary:
- reducer output represents the **current manual fallback facts**
- reducer output does **not** express a ledger tombstone, takeover, or cross-source retire event

If the current ingestion contract requires a minimal adapter for manual rows, that adapter must preserve existing Wave 3 identity semantics and must not redefine ledger identity.

### 3.8 Orchestration behavior in `etl/redemption_fetcher.py`

#### Normal run
If TuShare fetch succeeds:
- continue existing pipeline behavior
- manual command log does not override TuShare normal-path results
- no new cross-source merge policy is introduced by this PRD

#### Degraded daily run
If all of the following are true:
- this is **not** bootstrap
- TuShare fetch fails
- reduced manual facts are non-empty

Then:
- continue the pipeline in degraded mode using reduced manual facts as the fallback ingress source for this run
- mark freshness / status as degraded
- preserve the existing artifact-shape expectations of downstream outputs as much as possible
- avoid introducing new truth-boundary rules beyond what is necessary to complete the degraded run

#### Bootstrap failure
If the system lacks required baseline state and TuShare fetch fails:
- fail the pipeline
- do not allow manual-only bootstrap

#### Empty degraded fallback
If TuShare fetch fails and reduced manual facts are empty:
- fail with an explicit freshness/status outcome
- do not pretend the run succeeded

### 3.9 Canonical / ledger boundary

This PRD must not rely on a new theory of ledger truth.

Therefore:
- no Wave 3 identity migration
- no requirement to append new `SUPERSEDED` revisions for manual-to-TuShare takeover
- no requirement to introduce manual-overrides-active-TuShare semantics
- no requirement to express `CANCEL` as a ledger-level cross-source lifecycle action

If a later design wants manual/TuShare convergence inside one ledger stream, that work needs a separate architecture PRD.

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: Append DECLARE command**
  - **Given** `manual_events.csv` exists with a valid header
  - **When** the operator runs the CLI with `--command DECLARE` and all required fields
  - **Then** exactly one new CSV row is appended
  - **And** no previous row is modified or deleted

- **Scenario 2: Append CANCEL command**
  - **Given** `manual_events.csv` exists with prior command history for an identity
  - **When** the operator runs the CLI with `--command CANCEL` and valid required fields
  - **Then** exactly one new CSV row is appended
  - **And** `delisting_date` is empty in the appended row
  - **And** no previous row is modified or deleted

- **Scenario 3: Reduce DECLARE only**
  - **Given** command history for an identity ends with `DECLARE`
  - **When** the manual reducer processes the full command log
  - **Then** one manual ingress fact is emitted for that identity

- **Scenario 4: Reduce DECLARE then CANCEL**
  - **Given** command history for an identity contains `DECLARE` followed by `CANCEL`
  - **When** the manual reducer processes the full command log
  - **Then** no manual ingress fact is emitted for that identity

- **Scenario 5: Reduce DECLARE then CANCEL then DECLARE**
  - **Given** command history for an identity contains `DECLARE`, then `CANCEL`, then a later `DECLARE`
  - **When** the manual reducer processes the full command log
  - **Then** one manual ingress fact is emitted for that identity using the latest effective DECLARE data

- **Scenario 6: TuShare normal path remains primary**
  - **Given** a non-bootstrap daily run where TuShare fetch succeeds
  - **When** the pipeline executes
  - **Then** the existing TuShare normal path is used
  - **And** PRD B does not introduce manual override or cross-source takeover behavior into the successful TuShare path

- **Scenario 7: Degraded mode with manual fallback**
  - **Given** a non-bootstrap daily run where TuShare fetch fails
  - **And** the reduced manual facts are non-empty
  - **When** the pipeline executes
  - **Then** the run proceeds in explicit degraded mode
  - **And** the run uses reduced manual facts through the existing ingestion surface
  - **And** the resulting status/freshness output clearly indicates degraded/manual mode

- **Scenario 8: Bootstrap cannot use manual fallback**
  - **Given** required baseline state is absent
  - **And** TuShare fetch fails
  - **When** the pipeline executes
  - **Then** the pipeline fails
  - **And** manual fallback is not used to bootstrap the system

- **Scenario 9: Empty degraded fallback is not treated as success**
  - **Given** a non-bootstrap daily run where TuShare fetch fails
  - **And** the reduced manual facts are empty
  - **When** the pipeline executes
  - **Then** the run terminates with an explicit failure/empty-fallback status
  - **And** it is not reported as a normal successful sync

- **Scenario 10: No implicit architecture migration**
  - **Given** implementation work proceeds under PRD B
  - **When** downstream agents inspect the brief
  - **Then** they must not change the Wave 3 `event_id` / identity contract under this PRD
  - **And** they must not implement manual/TuShare unified-stream convergence logic under this PRD

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

### Core quality risk

The main risk is not the CLI itself. The main risk is **scope leakage**:
- accidentally changing Wave 3 identity semantics
- accidentally encoding cross-source lifecycle behavior under a fallback-only PRD
- making degraded mode look like a normal successful sync

### Verification strategy

1. **Reducer-focused unit tests**
   - verify append-only command history reduces deterministically
   - verify `DECLARE/CANCEL` state transitions
   - verify no reducer dependency on ledger state or runtime clock

2. **CLI behavior tests**
   - verify valid rows are appended exactly once
   - verify invalid argument combinations are rejected
   - verify no historical row is rewritten

3. **Pipeline orchestration tests**
   - mock TuShare fetch success/failure
   - verify degraded mode is entered only in the approved condition set
   - verify bootstrap still fails when TuShare is unavailable
   - verify empty manual fallback does not masquerade as success

4. **Boundary-protection tests**
   - verify no change to existing identity-contract behavior under PRD B
   - verify no cross-source takeover / supersede logic is introduced

### Mocking guidance

Mock:
- TuShare fetch responses
- filesystem reads of `manual_events.csv` where appropriate for orchestration tests
- time generation in CLI tests if timestamps are asserted

Avoid heavy E2E first. The most important quality signal is that:
- reducer behavior is deterministic
- degraded-mode gating is exact
- Wave 3 architecture remains unchanged

## 6. Framework Modifications (框架防篡改声明)

No leio-sdlc framework modification is authorized.

Authorized AMS project files only:
- `data/manual_events.csv`
- `scripts/manual_redemption_inject.py`
- `etl/manual_event_injector.py`
- `etl/redemption_fetcher.py`
- `etl/tushare_provider.py`
- `etl/cb_provider_base.py`

**EXPLICIT REFACTORING AUTHORIZATION:**
You are explicitly authorized to refactor `TuShareProvider.fetch_and_map_redemption_events` and base provider classes to distinguish genuine network/unavailability errors from generic runtime exceptions. This refactoring must be done so that degraded mode is ONLY triggered on actual network unavailability, preserving normal exception behavior for bugs.

If implementation requires deeper changes to ledger identity or cross-source lifecycle semantics, stop and return for a new PRD decision.

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: Drafts attempted to combine manual command log delivery with Wave 3 identity/lifecycle redesign.
- **Audit Rejection (earlier drafts)**: Rejections centered on hidden scope expansion: changing frozen `event_id` contract, introducing cross-source lifecycle semantics without migration planning, and overloading degraded mode with broader truth-boundary changes.
- **v2.0 Revision Rationale**: This rewrite deliberately narrows PRD B to a degraded-mode manual fallback path, defers source convergence, and explicitly forbids identity-contract migration under this PRD.

---

## 7. Hardcoded Content (硬编码内容)

### `manual_events.csv` header

```text
command,source_native_event_id,bond_code,announcement_date,delisting_date,reason,created_at
```

### CLI command enum

```text
DECLARE
CANCEL
```

### CLI parameter contract

```text
--command DECLARE|CANCEL (required)
--bond <bond_code> (required)
--ann <YYYY-MM-DD> (required)
--delist <YYYY-MM-DD> (required for DECLARE, forbidden/empty for CANCEL)
--reason <string> (required)
```

### Required degraded status strings

```text
MANUAL_DEGRADED
FRESHNESS_EMPTY
```

### Manual source string

```text
manual
```

### Exact scope-protection rule

```text
PRD B does not change the existing Wave 3 event_id / identity contract.
```

### Exact deferral rule

```text
Manual/TuShare unified-stream convergence, takeover, supersede, and identity migration are out of scope for PRD B.
```