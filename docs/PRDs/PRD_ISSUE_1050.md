---
Affected_Projects: [AMS]
---

# PRD: AMS Silence Rule Enforcement

## 1. Context & Problem Definition (核心问题与前因后果)
The boss has been receiving 'No new arbitrage opportunities' messages constantly from the AMS (Automated Market Screener) system. This creates unnecessary noise and alert fatigue, reducing the impact of actual positive signals. We need to enforce strict silence when no anomalies or opportunities are found to maintain a high signal-to-noise ratio.

## 2. Requirements (需求说明)
- Modify the AMS `SKILL.md` file.
- Add a new explicit rule to the 'Reasoning Protocol' section.
- The rule must state: '4. CRITICAL SILENCE RULE: If the tracker script outputs no new arbitrage opportunities or anomalies, you MUST reply with exactly and only NO_REPLY. Do not include any pleasantries, summaries, or other text. The entire response must be just the word NO_REPLY.'

## 3. Architecture (架构设计)
This is a prompt-level architectural change in the AMS AgentSkill. By enforcing the `NO_REPLY` behavior natively in the `SKILL.md`, the AMS agent will utilize OpenClaw's built-in silent reply mechanism, inherently suppressing its output when there is no actionable arbitrage data without requiring changes to the core tracker script.

## 4. Acceptance Criteria (验收标准)
- [ ] AMS `SKILL.md` is updated to include the new CRITICAL SILENCE RULE in the 'Reasoning Protocol' section.
- [ ] The rule explicitly mandates replying with exactly and only `NO_REPLY` when no opportunities are found.

## 5. Framework Modifications (框架修改声明)
- `SKILL.md` (within the AMS skill directory)

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: Initial draft to enforce NO_REPLY behavior in AMS for negative findings.
