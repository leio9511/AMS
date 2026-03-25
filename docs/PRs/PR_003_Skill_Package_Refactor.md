# PR-003: Refactor AMS into an OpenClaw Skill Package (Source vs Runtime Isolation)

## Goal
Refactor the AMS project into a standard AgentSkill structure within the Git repository. The project will maintain its source code in `/root/.openclaw/workspace/AMS/`, and use a `deploy.sh` script to install the skill to the OpenClaw runtime directory (`~/.openclaw/skills/ams/`). This enforces the industry standard of separating the Development Workspace from the Production Runtime.

## Scope
1. **Source Code Structure** (Inside `/root/.openclaw/workspace/AMS/`):
   - `SKILL.md` (The LLM instructions, version-controlled)
   - `scripts/etf_tracker.py` (The refactored Python script)
   - `deploy.sh` (The installation script)
2. **Runtime Target**: `~/.openclaw/skills/ams/`

## Contracts
### 1. The Skill Prompt (`SKILL.md`) - "Prompt-as-Code"
- Must be tracked in Git. It is the API contract for the LLM.
- **Reasoning Protocol**: Must instruct the LLM to verify purchase limits (限购) and index drops (外盘大跌) via `web_search` or logic before summarizing anomalies sent by the script.
- Must instruct the LLM to use the `message` tool to deliver the final curated report to the Boss.

### 2. The Data Pipe (`scripts/etf_tracker.py`)
- **NO TELEGRAM API**: Remove `send_msg_http()`. The script ONLY prints anomalies to stdout (e.g., JSON or Markdown).
- **STATEFUL THROTTLING**: Implement local caching (e.g., `cache/daily_alerts.json`). If an ETF was alerted today, exit silently. If no anomalies, exit silently.

### 3. The Deployment (`deploy.sh`)
- A simple bash script that creates `~/.openclaw/skills/ams/` and copies `SKILL.md` and `scripts/` to it.

## Acceptance Criteria (AC)
1. `etf_tracker.py` outputs ONLY stdout and has zero network messaging logic.
2. `SKILL.md` contains strict reasoning guidelines for the LLM.
3. `deploy.sh` successfully installs the package to the runtime skills directory.
4. `./preflight.sh` passes successfully.

## Anti-Patterns
- **DO NOT** develop directly inside `~/.openclaw/skills/`. Always develop in the workspace and deploy.
- **DO NOT** let the python script bypass the LLM. The script prints; the LLM reads, thinks, and sends.
