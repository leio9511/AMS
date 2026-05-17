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

The intended semantics are *incremental post-baseline fallback*, not *manual truth replacement*:
- if a healthy authoritative baseline already exists, operators may provide manual facts only for the missing run window since the last successful authoritative sync
- if TuShare is unavailable only for the current day, operators provide only the current-day missing increment (or an explicit no-new-events degraded outcome)
- if TuShare is unavailable during bootstrap / cold start, manual fallback is not allowed to stand in for full historical source reconstruction
- if the system cannot establish the required historical baseline from TuShare, the pipeline must fail closed rather than request manual reconstruction of full history
- manual fallback is therefore limited to target-date / missing-window degraded execution and is never a substitute for bootstrap or historical backfill

This PRD must stay narrowly scoped. The goal is **not** to redesign Wave 3 identity semantics or unify manual and TuShare into a single business-event stream. That larger problem exists, but it is not approved inside PRD B.

### Frozen design baseline for this PRD

1. **Wave 3 event identity contract is frozen in this PRD.**
   This PRD does **not** change existing `event_id` / identity semantics.

2. **TuShare remains the primary authoritative upstream source for normal operation.**
   This PRD addresses temporary source unavailability, not semantic correction of trusted TuShare content.

3. **Manual input is a degraded-mode operational fallback.**
   It is not a general source-convergence mechanism and not a long-term replacement for TuShare.
   Its effect is limited to post-baseline degraded runs and must not create long-lived manual truth inside the permanent Wave 3 ledger path.

4. **Bootstrap cannot be replaced by manual input.**
   If the system lacks the required baseline and TuShare is unavailable, the pipeline must fail.
   Manual fallback is valid only after at least one successful authoritative baseline exists.

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
  `scripts/manual_redemption_inject.py` appends `DECLARE` or `CANCEL` rows to `manual_events.csv`, performs basic argument validation over business fields only, and works together with an explicit operator-completion step for the target-date degraded fallback workflow.

- **FR3 — Deterministic reduce of manual command history**
  A pure transform reduces the append-only command history by a deterministic system-derived `source_native_event_id` into the latest manual state for each identity.

- **FR3A — Explicit completion boundary for empty manual input**
  PRD B must define an explicit operator-completion protocol for target-date degraded fallback review. Zero event-bearing manual rows may be interpreted as `MANUAL_NO_EVENTS` only after that completion step is explicitly recorded.

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
- do not persist manual fallback rows as long-lived Wave 3 ledger truth revisions
- keep manual fallback effects confined to run-scoped effective state and same-day operational outputs

### 3.4 `manual_events.csv` schema

`manual_events.csv` is append-only and git-tracked.

This file records **summarized same-day degraded fallback facts**, not raw per-announcement detail.
For PRD B, the operator is responsible for consolidating multiple same-day announcements for the same bond into one final redemption-related fact before CLI submission.
PRD B does not model raw announcement archival or multi-announcement merge semantics inside the system.
`manual_events.csv` stores only event-bearing manual command rows. It does not require per-bond explicit “no event” rows.

Schema:

```text
command,source_native_event_id,bond_code,announcement_date,delisting_date,reason,created_at
```

Rules:
- `command` is `DECLARE` or `CANCEL`
- `announcement_date` is the target-date identity boundary for PRD B manual fallback
- at most one logical manual fact may exist per `(bond_code, announcement_date)` pair within PRD B degraded fallback scope
- `source_native_event_id` is a system-derived deterministic identity key generated from the approved business input fields for the summarized same-day manual fact; operators do not provide it directly
- `delisting_date` is required for `DECLARE`
- `delisting_date` must be empty for `CANCEL`
- `reason` is required for both commands
- `created_at` is written by the CLI at append time

Deterministic identity rule for this PRD:
- `source_native_event_id` must be derived internally from the exact tuple `(bond_code, announcement_date)`
- `delisting_date`, `reason`, and `command` must not participate in identity derivation
- a later `CANCEL` or re-`DECLARE` targets the same logical summarized same-day manual fact only if it is issued with the same `(bond_code, announcement_date)` pair
- `CANCEL` revokes a previously entered manual fallback fact in the append-only command log; it is not a claim that the real-world announcement itself was cancelled
- if multiple announcements exist for the same bond on the same date, the operator must consolidate them into one final fact before CLI entry; PRD B does not support multiple independent same-day facts for one bond
- if a future design needs raw announcement-level modeling or multiple same-day facts for the same bond/date pair, that is a new PRD rather than an implementation choice inside PRD B

Example:

```csv
DECLARE,123456.SH_2026-05-15,123456.SH,2026-05-15,2026-06-20,TuShare API unavailable,2026-05-15T10:00:00Z
CANCEL,123456.SH_2026-05-15,123456.SH,2026-05-15,,wrong manual entry,2026-05-15T11:00:00Z
```

### 3.5 CLI contract

`manual_redemption_inject.py` is a thin append-only writer for **summarized same-day degraded fallback facts**.

Responsibilities:
- validate required arguments
- normalize command casing
- enforce `DECLARE` vs `CANCEL` field rules
- derive `source_native_event_id` internally from the PRD-approved business input tuple `(bond_code, announcement_date)` using one documented deterministic rule
- append exactly one CSV row
- never rewrite prior rows
- support a separate explicit operator-completion step for the target-date degraded fallback review workflow

Non-responsibilities:
- no raw per-announcement archival
- no automatic multi-announcement merge logic
- no ledger reads
- no source-convergence logic
- no takeover logic
- no canonical regeneration logic
- no ledger-level cancellation or durable-truth revocation semantics

### 3.6 Reduction model

`etl/manual_event_injector.py` reduces command history per system-derived `source_native_event_id`.

Reducer semantics:
- latest effective `DECLARE` => emit one active summarized same-day manual fact
- latest effective `CANCEL` => emit no manual fact for that identity
- `DECLARE -> CANCEL -> DECLARE` => final DECLARE wins
- `CANCEL` with no preceding DECLARE in command history => reduced output is empty for that identity
- `CANCEL` is operationally a revocation of a previously entered manual fallback fact before durable-truth persistence; it does not define a ledger-level cancellation lifecycle for long-lived Wave 3 truth

This reducer is intentionally **command-log local**.
It does not inspect ledger history and does not attempt to encode post-ingestion lifecycle.
It also does not implement raw announcement-level merge semantics; the operator must already have consolidated same-day multiple announcements into one final fact before CLI submission.

### 3.7 Output of manual reducer

The reducer outputs a DataFrame matching the existing ingestion surface used for redemption facts, with `source="manual"` populated for rows originating from the reduced manual state.

**Frozen ingress-schema contract for PRD B:**
For this PRD, the authoritative manual-fallback ingress schema is explicitly frozen to `redemption_ledger.IMPORT_COLUMNS`.
That schema is the required output shape of `etl/manual_event_injector.py` for downstream consumption in this PRD.

Required downstream compatibility rule:
- within the scope of PRD B, `etl/redemption_fetcher.py`, `etl/tushare_provider.py`, and any minimal adapter logic must treat `redemption_ledger.IMPORT_COLUMNS` as the canonical manual-fallback ingress contract
- downstream implementation may add explicit contract assertions or adapter checks, but must not require additional ingress columns for PRD B manual-fallback rows unless this PRD is amended
- reviewer acceptance for PRD B must evaluate reducer/fetcher/provider compatibility against this frozen six-column ingress contract, not against a broader implied schema that is not explicitly defined here

Important boundary:
- reducer output represents the **current manual fallback facts**
- reducer output does **not** express a ledger tombstone, takeover, or cross-source retire event

If the current ingestion contract requires a minimal adapter for manual rows, that adapter must preserve existing Wave 3 identity semantics and must not redefine ledger identity.

### 3.8 Orchestration behavior in `etl/redemption_fetcher.py`

#### Operational-state model for degraded runs
This PRD freezes a two-layer model:
- **authoritative long-lived truth** = the normal Wave 3 ledger/canonical path produced from successful TuShare-based authoritative runs
- **run-scoped effective state** = the operational state used by the current degraded run to drive same-day outputs when authoritative upstream is temporarily unavailable

Under PRD B:
- reduced manual fallback facts may affect the run-scoped effective state
- reduced manual fallback facts may drive same-day outputs, reports, and operational decisions for that degraded run
- reduced manual fallback facts must **not** be persisted as long-lived manual ledger truth that survives as a permanent parallel source after TuShare recovery
- the durable audit trail for manual intervention is `data/manual_events.csv`, not permanent manual truth rows in the Wave 3 ledger
- when TuShare recovers, the next successful authoritative run replaces degraded operational state rather than converging with or coexisting alongside permanent manual ledger truth
- PRD B assumes operator mistakes in manual entry are corrected before durable-truth persistence through append-only command-log revocation (`CANCEL`) and re-reduction of the current effective manual state

#### Frozen file-boundary contract for degraded runs
To keep the truth boundary implementable and auditable, PRD B explicitly freezes what degraded runs may and may not write.

**Degraded runs may write only run-scoped operational artifacts such as:**
- the append-only audit trail in `data/manual_events.csv`
- a run-scoped import artifact used only for the current degraded execution path
- run-scoped freshness / status / report artifacts that explicitly describe degraded/manual operation
- a run-scoped effective-state snapshot or equivalent temporary operational artifact, if needed, provided it is clearly not the long-lived authoritative Wave 3 truth layer

**Degraded runs must not write or mutate as durable truth artifacts:**
- the long-lived Wave 3 ledger truth file as if manual fallback rows were authoritative durable events
- the long-lived canonical truth artifact as if degraded manual fallback were equivalent to a successful authoritative TuShare refresh
- any persistent parallel manual-truth layer that survives as a second source after TuShare recovery

Required recovery rule:
- the next successful authoritative TuShare-based run is the only allowed mechanism for refreshing long-lived ledger/canonical truth after a degraded period
- degraded-run operational artifacts may be replaced, superseded, or discarded on recovery without requiring cross-source convergence semantics

Required isolation point:
- if the current `run_redemption_wave3_pipeline` only produces durable ledger/canonical truth artifacts, PRD B must introduce or use a minimal isolated degraded-run path / adapter boundary so same-day outputs can be produced without persisting manual fallback rows as long-lived truth
- PRD B does **not** authorize silently reusing the durable-truth pipeline in a way that writes manual fallback rows into permanent truth files while merely relabeling them as temporary

#### Normal run
If TuShare fetch succeeds:
- continue existing pipeline behavior
- manual command log does not override TuShare normal-path results
- no new cross-source merge policy is introduced by this PRD

#### Degraded daily run
If all of the following are true:
- this is **not** bootstrap
- a prior authoritative baseline exists
- TuShare fetch fails due to **network / upstream unavailability**
- reduced manual facts for the missing run window are non-empty

Then:
- continue the pipeline in degraded mode using reduced manual facts as the fallback ingress source for this run
- apply those facts only to the run-scoped effective state for that degraded run
- mark freshness / status as degraded
- preserve the existing artifact-shape expectations of downstream outputs as much as possible
- avoid introducing new truth-boundary rules beyond what is necessary to complete the degraded run

#### Failure-class taxonomy for degraded-mode gating
This PRD now freezes the failure-boundary contract that downstream implementation must make explicit and testable.

Approved failure classes:
- **NETWORK_UNAVAILABLE** — upstream network failure, upstream service unavailable, timeout, transport-layer interruption, or equivalent TuShare unavailability condition. This is the **only** failure class that may trigger degraded-mode fallback.
- **AUTH_FAILED** — invalid token, revoked credential, permission denial, or equivalent authentication / authorization failure. This must **not** trigger degraded mode.
- **QUOTA_EXCEEDED** — provider-side quota exhaustion, throttling limit, or equivalent rate / allowance failure. This must **not** trigger degraded mode.
- **RUNTIME_BUG** — programmer bug, unexpected mapping/parsing/runtime exception, schema bug, or other non-provider implementation defect. This must **not** trigger degraded mode.

Required implementation contract:
- `etl/tushare_provider.py` and supporting provider/base-provider code are authorized to introduce the smallest necessary explicit exception/status taxonomy so these classes can be distinguished deterministically.
- `etl/redemption_fetcher.py` must only enter degraded mode when the observed failure class is `NETWORK_UNAVAILABLE`.
- `AUTH_FAILED`, `QUOTA_EXCEEDED`, and `RUNTIME_BUG` must fail closed and remain externally distinguishable from degraded-mode execution.
- It is forbidden to collapse all failures into one generic fallback-eligible bucket if that would allow non-network failures to continue in degraded mode.

Required observable status contract:
- successful degraded fallback run → pipeline status `MANUAL_DEGRADED`
- network/unavailability failure + empty reduced manual facts → explicit empty-fallback failure status `FRESHNESS_EMPTY`
- bootstrap/baseline absent when fallback would otherwise be needed → explicit status `BOOTSTRAP_REQUIRED`
- auth failure → explicit auth failure status `AUTH_FAILED`
- quota failure → explicit quota failure status `QUOTA_EXCEEDED`
- runtime/programmer bug → explicit non-degraded hard failure status `RUNTIME_BUG`

The exact internal exception class names may be implementation-defined, but the above black-box behavioral separation is mandatory.

#### Bootstrap failure
If the system lacks required baseline state and TuShare fetch fails:
- fail the pipeline with explicit status `BOOTSTRAP_REQUIRED`
- do not allow manual-only bootstrap

#### Empty degraded fallback
If TuShare fetch fails for the missing run window and reduced manual facts are empty:
- this must not be treated as a normal successful authoritative TuShare run by default
- if the operator has explicitly completed the target-date manual review workflow and submitted zero event-bearing manual rows, the run may complete with explicit `MANUAL_NO_EVENTS` degraded semantics
- if the system required event-bearing fallback facts for the missing run window and no explicit operator-completion signal exists, the run must fail with explicit `FRESHNESS_EMPTY`
- under no circumstance may the system interpret empty manual fallback as permission to fabricate historical/manual backfill beyond the target run window

#### Explicit operator-completion boundary for empty manual input
PRD B requires an explicit operator-completion protocol for target-date degraded fallback review.
This may be implemented as a finalize CLI action, a completion marker artifact, or an equivalent explicit control-plane signal.
The protocol contract is frozen as follows:
- before the completion signal exists, zero manual event rows are ambiguous and must not be interpreted as `MANUAL_NO_EVENTS`
- after the completion signal exists, zero event-bearing manual rows for the target date mean `MANUAL_NO_EVENTS`
- the operator records only bonds with event-bearing facts; bonds omitted from a completed target-date manual review are implicitly treated as having no event for that date
- if the operator completes the manual review and records zero event-bearing rows, the semantic meaning is “no relevant redemption-related events were found for the target date across the reviewed universe”

#### No-new-events degraded outcome
If TuShare fetch fails for the missing run window, a prior authoritative baseline exists, the operator explicitly completes the manual review workflow for the target date, and zero event-bearing manual rows are submitted:
- the degraded run may complete with an explicit no-new-events operational outcome rather than inventing business events
- this outcome must be externally distinguishable from both normal TuShare success and event-bearing manual fallback
- this outcome must not require explicit per-bond `NO_EVENTS` rows or ambiguous free-form placeholders such as raw `N/A` business-event rows
- this outcome must be surfaced using the frozen externally observable status string `MANUAL_NO_EVENTS`

### 3.9 Canonical / ledger boundary

This PRD must not rely on a new theory of ledger truth.

Therefore:
- no Wave 3 identity migration
- no requirement to append new `SUPERSEDED` revisions for manual-to-TuShare takeover
- no requirement to introduce manual-overrides-active-TuShare semantics
- no requirement to express `CANCEL` as a ledger-level cross-source lifecycle action
- if erroneous manual-derived durable truth is ever persisted outside PRD B’s intended run-scoped boundary, recovery is an operational rebuild concern using authoritative TuShare data once available, not an in-PRD-B ledger-level cancellation protocol

If a later design wants manual/TuShare convergence inside one ledger stream, that work needs a separate architecture PRD.

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: Append DECLARE command**
  - **Given** `manual_events.csv` exists with a valid header
  - **When** the operator runs the CLI with `--command DECLARE` and all required business fields
  - **Then** exactly one new CSV row is appended
  - **And** no previous row is modified or deleted
  - **And** the CLI derives `source_native_event_id` internally from `(bond_code, announcement_date)` rather than requiring an explicit identity argument
  - **And** the appended row represents one summarized same-day manual fact rather than raw per-announcement detail

- **Scenario 2: Append CANCEL command**
  - **Given** `manual_events.csv` exists with prior command history for an identity
  - **When** the operator runs the CLI with `--command CANCEL` and valid required business fields using the same `(bond_code, announcement_date)` pair as the target prior DECLARE
  - **Then** exactly one new CSV row is appended
  - **And** `delisting_date` is empty in the appended row
  - **And** no previous row is modified or deleted

- **Scenario 2A: Same-day multiple announcements are consolidated before entry**
  - **Given** a bond has multiple relevant announcements on the same target date
  - **When** the operator uses the PRD B manual CLI
  - **Then** the operator records only one final summarized manual fact for that bond/date
  - **And** PRD B does not accept multiple independent same-day facts for the same `(bond_code, announcement_date)` pair
  - **And** raw per-announcement detail is out of scope for this manual fallback path

- **Scenario 2B: Explicit operator-completion makes zero rows auditable**
  - **Given** a target-date degraded manual review completes with no event-bearing facts to add
  - **When** the operator submits the PRD B completion signal for that target date
  - **Then** the system has sufficient evidence to distinguish explicit completed no-events review from silent empty fallback
  - **And** no explicit per-bond `NO_EVENTS` row is required

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
  - **Given** a non-bootstrap daily run where TuShare fails with a `NETWORK_UNAVAILABLE`-class failure
  - **And** a prior authoritative baseline exists
  - **And** the reduced manual facts for the missing run window are non-empty
  - **When** the pipeline executes
  - **Then** the run proceeds in explicit degraded mode
  - **And** the run uses reduced manual facts through the existing ingress surface for that degraded run
  - **And** the resulting status/freshness output clearly indicates degraded/manual mode
  - **And** the manual fallback affects run-scoped effective state rather than becoming long-lived permanent manual ledger truth

- **Scenario 8: Bootstrap cannot use manual fallback**
  - **Given** required baseline state is absent
  - **And** TuShare fails with a `NETWORK_UNAVAILABLE`-class failure
  - **When** the pipeline executes
  - **Then** the pipeline fails with explicit status `BOOTSTRAP_REQUIRED`
  - **And** manual fallback is not used to bootstrap the system
  - **And** operators are not required to reconstruct full historical source data by hand

- **Scenario 9: Empty degraded fallback is not treated as success**
  - **Given** a non-bootstrap daily run where TuShare fails with a `NETWORK_UNAVAILABLE`-class failure
  - **And** a prior authoritative baseline exists
  - **And** the reduced manual facts for the missing run window are empty
  - **When** the pipeline executes
  - **Then** the run terminates with explicit empty-fallback failure status `FRESHNESS_EMPTY`
  - **And** it is not reported as a normal successful sync

- **Scenario 10: Auth failure never triggers degraded mode**
  - **Given** a non-bootstrap daily run where TuShare fails with an `AUTH_FAILED`-class failure
  - **When** the pipeline executes
  - **Then** degraded mode is not entered
  - **And** the run fails closed with explicit auth-failure status `AUTH_FAILED`
  - **And** reduced manual facts are not used as fallback ingress

- **Scenario 11: Quota failure never triggers degraded mode**
  - **Given** a non-bootstrap daily run where TuShare fails with a `QUOTA_EXCEEDED`-class failure
  - **When** the pipeline executes
  - **Then** degraded mode is not entered
  - **And** the run fails closed with explicit quota-failure status `QUOTA_EXCEEDED`
  - **And** reduced manual facts are not used as fallback ingress

- **Scenario 12: Runtime/programmer bug never triggers degraded mode**
  - **Given** a non-bootstrap daily run where upstream fetch/mapping fails with a `RUNTIME_BUG`-class failure
  - **When** the pipeline executes
  - **Then** degraded mode is not entered
  - **And** the run fails closed with explicit hard-failure status `RUNTIME_BUG`
  - **And** reduced manual facts are not used as fallback ingress

- **Scenario 13: Explicit no-new-events degraded outcome**
  - **Given** a non-bootstrap daily run where TuShare fails with a `NETWORK_UNAVAILABLE`-class failure
  - **And** a prior authoritative baseline exists
  - **And** the operator explicitly completes the target-date manual review workflow
  - **And** zero event-bearing manual rows were submitted for that completed review
  - **When** the degraded run executes
  - **Then** the run completes with explicit no-new-events status `MANUAL_NO_EVENTS`
  - **And** that outcome is distinct from normal success and distinct from event-bearing manual fallback
  - **And** the system does not fabricate business-event rows using ambiguous placeholder values such as raw `N/A`

- **Scenario 14: Reducer output matches the frozen PRD B ingress contract**
  - **Given** reduced manual command history is emitted for downstream ingestion under PRD B
  - **When** the reducer returns manual fallback rows
  - **Then** the output schema matches `redemption_ledger.IMPORT_COLUMNS`
  - **And** fetcher/provider-side PRD B integration accepts that schema as sufficient manual-fallback ingress without requiring additional implicit columns

- **Scenario 15: Degraded run writes only allowed operational artifacts**
  - **Given** a degraded run executes using manual fallback
  - **When** downstream artifacts are inspected
  - **Then** only the PRD-approved run-scoped operational artifacts are written for degraded operation
  - **And** the degraded run does not persist manual fallback rows as durable Wave 3 ledger truth or durable canonical truth

- **Scenario 16: TuShare recovery replaces degraded operational state**
  - **Given** a prior degraded run used manual fallback to produce run-scoped effective state
  - **And** a later run succeeds from authoritative TuShare input
  - **When** the recovery run completes
  - **Then** the authoritative run replaces degraded operational state for future runs
  - **And** the system does not require manual/TuShare long-term coexistence or cross-source convergence to restore normal operation

- **Scenario 17: No implicit architecture migration**
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

2. **CLI / completion behavior tests**
   - verify valid rows are appended exactly once
   - verify invalid argument combinations are rejected
   - verify no historical row is rewritten
   - verify explicit operator-completion semantics for zero-row target-date review

3. **Pipeline orchestration tests**
   - mock TuShare fetch success/failure
   - verify degraded mode is entered only in the approved post-baseline condition set
   - verify bootstrap still fails when TuShare is unavailable
   - verify empty manual fallback does not masquerade as success
   - verify explicit no-new-events degraded outcome behavior
   - verify auth failures never enter degraded mode
   - verify quota failures never enter degraded mode
   - verify runtime/programmer bugs never enter degraded mode
   - verify each failure class emits its required externally observable status
   - verify TuShare recovery replaces degraded operational state on the next successful authoritative run

4. **Boundary-protection tests**
   - verify no change to existing identity-contract behavior under PRD B
   - verify no cross-source takeover / supersede logic is introduced
   - verify degraded-mode gating is fail-closed for all non-network failure classes
   - verify manual reducer output and downstream PRD B integration both anchor to `redemption_ledger.IMPORT_COLUMNS` as the frozen ingress contract
   - verify manual fallback effects remain run-scoped and do not create long-lived parallel manual ledger truth
   - verify degraded runs write only the explicitly allowed operational artifacts and do not mutate durable truth artifacts

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
- **v2.1 Clarification Rationale**: This revision further clarifies that PRD B manual fallback records one summarized same-day fact per bond/date, not raw per-announcement detail, and that any same-day multi-announcement interpretation must be consolidated by the operator before CLI submission.
- **v2.2 Clarification Rationale**: This revision removes row-level `NO_EVENTS` commands in favor of an explicit operator-completion boundary: operators record only event-bearing facts, omitted bonds are implicitly no-event after completed review, and `CANCEL` is limited to revoking previously entered manual fallback facts before durable-truth persistence.

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

### Deterministic identity derivation contract

```text
source_native_event_id is system-derived from exactly (bond_code, announcement_date).
The CLI must not require or accept an operator-supplied source_native_event_id.
CANCEL and later DECLARE commands target the same logical summarized same-day manual fact only when they reuse the same bond_code + announcement_date pair.
```

### Operator completion contract for empty manual review

```text
Operators record only event-bearing facts for target-date degraded fallback review.
Bonds omitted from a completed target-date manual review are implicitly treated as no-event for that date.
Zero event-bearing rows may be interpreted as MANUAL_NO_EVENTS only after an explicit operator-completion signal is recorded.
Before that completion signal exists, zero rows remain ambiguous and must not be treated as MANUAL_NO_EVENTS.
```

### Same-day manual fact consolidation rule

```text
For PRD B degraded manual fallback, the operator records one summarized same-day redemption fact per (bond_code, announcement_date).
If multiple relevant announcements exist for the same bond on the same date, the operator must consolidate them into one final fact before CLI submission.
PRD B does not support multiple independent same-day facts for the same bond/date pair and does not model raw per-announcement archival.
CANCEL only revokes a previously entered manual fallback fact before durable-truth persistence; ledger-level cancellation semantics are out of scope for PRD B.
```

### Required degraded status strings

```text
MANUAL_DEGRADED
FRESHNESS_EMPTY
MANUAL_NO_EVENTS
AUTH_FAILED
QUOTA_EXCEEDED
RUNTIME_BUG
BOOTSTRAP_REQUIRED
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