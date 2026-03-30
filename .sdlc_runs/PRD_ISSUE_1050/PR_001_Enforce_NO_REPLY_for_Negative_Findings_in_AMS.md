status: in_progress

# PR-001: Enforce NO_REPLY for Negative Findings in AMS

## 1. Objective
Add a strict silence rule to the AMS agent's reasoning protocol to prevent noise and alert fatigue when no arbitrage opportunities are found.

## 2. Scope (Functional & Implementation Freedom)
- Locate the agent skill configuration/prompt file for the AMS system.
- Add a new explicit rule to the "Reasoning Protocol" section mandating the exact output of `NO_REPLY` when no anomalies or opportunities are found.
- Ensure no pleasantries or summaries are included in this negative case.
*The Coder MUST search the workspace, understand the existing code structure, and autonomously decide which files to create or modify to implement this logic.*

## 3. TDD & Acceptance Criteria
1. The AMS skill definition explicitly contains the "CRITICAL SILENCE RULE" in its reasoning protocol.
2. The rule mandates replying with exactly and only `NO_REPLY` when no opportunities are found.
3. Verify that the changes do not break the existing markdown structure of the skill definition.
