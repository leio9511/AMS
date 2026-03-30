---
Affected_Projects: [AMS]
---

# PRD: AMS SKILL.md Sync Hotfix (Issue 1045)

## 1. Context & Problem Definition (核心问题与前因后果)
The AMS project currently has a discrepancy between its runtime deployment and its codebase source of truth. The runtime `SKILL.md` was recently hotfixed to remove the deprecated `message` tool in favor of native `announce` delivery. However, the codebase version located at `/root/.openclaw/workspace/projects/AMS/SKILL.md` still relies on the old prompt structure. If left unsynced, the next deployment will overwrite the runtime hotfix, causing a regression back to the deprecated message tool.

## 2. Requirements (需求说明)
- Update the codebase `SKILL.md` for AMS (`/root/.openclaw/workspace/projects/AMS/SKILL.md`) to reflect the runtime hotfix.
- Remove all references and instructions related to the deprecated `message` tool.
- Replace the removed tool instructions with the native `announce` delivery mechanism logic.
- Ensure the structural integrity of the `SKILL.md` remains intact for the AMS system.

## 3. Architecture (架构设计)
This is a configuration/prompt sync update, not a code architecture change. The update targets the LLM system prompt definition (`SKILL.md`) for the AMS agent to conform to OpenClaw's modern delivery specifications (native announce).

## 4. Acceptance Criteria (验收标准)
- [ ] `/root/.openclaw/workspace/projects/AMS/SKILL.md` no longer contains instructions to use the `message` tool.
- [ ] `/root/.openclaw/workspace/projects/AMS/SKILL.md` includes explicit instructions for native `announce` delivery.
- [ ] The `SKILL.md` successfully validates against the latest OpenClaw AgentSkill specification.

## 5. Framework Modifications (框架修改声明)
- /root/.openclaw/workspace/projects/AMS/SKILL.md

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: Initial PRD drafted to sync codebase SKILL.md with the runtime native announce delivery hotfix.
