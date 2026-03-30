---
Affected_Projects: [AMS, openclaw_native_patterns]
---

# PRD: AMS Notification Migration & Architecture Doc Update (Issue #1045)

## 1. Context & Problem Definition (核心问题与前因后果)
The Auditor rejected the previous PRD due to platform/mechanism mismatches and missing architecture documentation updates. The AMS project currently uses a deprecated `message` tool with a hardcoded Telegram ID. We need to modernize the notification pipeline to utilize OpenClaw's native announce routing (which defaults to Slack) and implement a robust spam prevention mechanism for cron jobs. Furthermore, the global architecture documentation (`openclaw_native_patterns.md` Pattern 4) still explicitly mandates the legacy `message` tool usage and must be updated to reflect the new architectural standard of using native conversational text output and `NO_REPLY` for suppression.

## 2. Requirements (需求说明)
- **RQ-1 (Tool Removal):** The `SKILL.md` must be updated to explicitly remove any reference to the `message` tool and the hardcoded `telegram:6228532305` routing.
- **RQ-2 (Native Output):** The LLM must be instructed to output its anomaly report directly as conversational text.
- **RQ-3 (Spam Prevention):** The LLM must be instructed to output EXACTLY and ONLY `NO_REPLY` if the data yields no anomalies, ensuring the cron job does not spam the Slack channel.
- **RQ-4 (Architecture Doc Update):** Update Pattern 4 in `/root/.openclaw/workspace/projects/docs/TEMPLATES/openclaw_native_patterns.md` to reflect the new architectural standard: The Manager should output the report directly as conversational text, which the native announce feature will automatically route. To suppress noise (e.g., cron runs), the LLM must output exactly and only 'NO_REPLY'.

## 3. Architecture (架构设计)
- **Notification Routing**: Leverage OpenClaw's native cron `announce` feature which automatically routes standard text output to the designated channel (Slack).
- **Spam Suppression**: By outputting `NO_REPLY`, the system native message handler will suppress the output entirely, solving the 5-minute cron spam issue efficiently without additional tool overhead.
- **Global Pattern Update**: Synchronize the `openclaw_native_patterns.md` global template to ensure future agents adopt this native routing pattern instead of hallucinating legacy tool usage.

## 4. Acceptance Criteria (验收标准)
- [ ] `SKILL.md` no longer contains references to the `message` tool or `telegram:6228532305`.
- [ ] `SKILL.md` instructs the LLM to output conversational text for anomalies and `NO_REPLY` when there are no anomalies.
- [ ] Pattern 4 in `/root/.openclaw/workspace/projects/docs/TEMPLATES/openclaw_native_patterns.md` is rewritten to state that the Manager outputs the report directly as conversational text and uses `NO_REPLY` for noise suppression.

## 5. Framework Modifications (框架修改声明)
- `/root/.openclaw/workspace/projects/docs/TEMPLATES/openclaw_native_patterns.md`

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: Initial draft to remove `message` tool and migrate to native Slack routing with `NO_REPLY` suppression.
- **Audit Rejection (v1.0)**: Rejected by Auditor. Missed updating the global architecture documentation `openclaw_native_patterns.md` which still mandates the legacy `message` tool.
- **v2.0 Revision Rationale**: Added requirements, acceptance criteria, and framework modifications to update Pattern 4 in the global architecture documentation to reflect the new native announce and `NO_REPLY` standard.