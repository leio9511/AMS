---
Affected_Projects: [AMS]
---

# PRD: AgentSkill_Integration

## 1. Context & Problem (业务背景与核心痛点)
The AMS (Automated Market Screener) currently functions as a passive execution engine. To make it a "Family Office" level private wealth manager, it must be encapsulated as an OpenClaw AgentSkill. This allows the Boss to use natural language to query market spreads, run on-demand stock screens (e.g. Crystal Fly), manage a multi-asset global ledger, and set up dynamic sentinel alerts. The system needs "Brain and Pipe" separation: Python acts as the stateless pipe, LLM acts as the brain.

## 2. Requirements & User Stories (需求定义)
Build the `ams` AgentSkill with the following 4 core capabilities:
1. **Dynamic Market Spread Radar**: Query QMT tick data for ETFs/CBs and calculate premiums on demand.
2. **On-demand Screener**: Accept dynamic parameters (e.g., PE < 15) to filter the A-share market using locally cached financial fundamentals.
3. **Global Portfolio Ledger**: Maintain a persistent state using SQLite to track stocks, funds, and real estate, updating valuations and calculating dynamic PnL. The database must be completely isolated from Git version control.
4. **Dynamic Sentinel Alerts**: Register heartbeat-driven background tasks based on natural language instructions.

The system will enforce a strict Dev vs. Prod isolation. The backend Python scripts will be co-located with `SKILL.md` in the runtime directory (`~/.openclaw/skills/ams/`).

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **Dev Workspace**: `/root/.openclaw/workspace/projects/AMS/` (for coding and testing).
- **Prod Runtime (AgentSkill)**: `~/.openclaw/skills/ams/` (contains `SKILL.md` and `scripts/`).
- **Data Persistence (State)**: 
  - The portfolio ledger must be implemented using SQLite (`ledger.db`).
  - To achieve strict Prod/Dev isolation and prevent accidental deletion via git commands, the database must be stored in a dedicated system-level data directory outside the workspace: `~/.openclaw/data/ams/ledger.db`.
- **Data Flow**: User Intent -> OpenClaw LLM matches `SKILL.md` -> LLM executes `python3 ~/.openclaw/skills/ams/scripts/...` -> Script outputs JSON -> LLM interprets and replies to User.
- **Deploy Pipeline (`deploy.sh`)**: Must perform Three-in-One deployment:
  1. Copy `SKILL.md` and `scripts/*.py` to the Prod Runtime directory.
  2. Remotely deploy Windows bridge/ETL scripts via SSH to the QMT node.
  3. Perform pre-flight environment checks (ensure `~/.openclaw/data/ams/` exists).
- **Disaster Recovery (Backup)**: The backup and SCP transfer logic (including Windows auth) must be strictly encapsulated in a stateless Python script (`scripts/backup_ledger.py`). During deployment, use the OpenClaw native `cron` tool (`openclaw cron add`) to register a daily task where the Agent simply invokes this script and summarizes the result, preventing the LLM from hallucinating deterministic network operations.

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1:** User asks for current 159501 spread
  - **Given** the AMS skill is loaded in the agent's runtime,
  - **When** the user queries "What is the premium of 159501?",
  - **Then** the agent invokes the spread Python script, parses the JSON, and returns the latest tick premium in human-readable text.

- **Scenario 2:** User adds a real estate asset to the ledger
  - **Given** the SQLite portfolio ledger exists in `~/.openclaw/data/ams/`,
  - **When** the user says "Add a house worth 5m to my portfolio",
  - **Then** the agent invokes the ledger update script, updating the SQLite database and confirming the new total asset value.

- **Scenario 3:** Deploy script execution and state preservation
  - **Given** a fresh checkout or update in AMS dev workspace,
  - **When** `./deploy.sh` is run,
  - **Then** the `ams` skill is correctly published to `~/.openclaw/skills/ams/`, Windows node scripts are updated via SSH, and the system-level `~/.openclaw/data/ams/ledger.db` remains intact and unaffected by deployment.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Integration Test**: Use `skill_test_runner` to simulate conversation replays for the 4 core capabilities.
- **Unit Test**: Test the Python data pipes (SQLite CRUD operations, QMT tick fetcher) directly via Pytest in the Dev Workspace.
- **Mocking**: Mock the Windows QMT API responses (JSON payload) during CI runs to avoid test flakiness due to network or market closure.

## 6. Framework Modifications (框架防篡改声明)
- None

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**

### Exact Text Replacements:

- **For `~/.openclaw/skills/ams/SKILL.md` (Replace entire file)**:
```markdown
---
name: ams
description: Automated Market Screener & Global Portfolio Ledger. Use this skill to query ETF/CB premiums, screen A-share stocks (e.g. Crystal Fly), manage the global portfolio ledger, and set up dynamic sentinel alerts.
---

# AMS AgentSkill

You are equipped with the AMS toolset. To answer questions about market data or portfolios, strictly use the `exec` tool to run the following Python pipes and interpret their JSON output.

1. **Market Spread Radar**: 
   `python3 ~/.openclaw/skills/ams/scripts/query_spread.py --ticker <TICKER>`
2. **On-demand Screener**: 
   `python3 ~/.openclaw/skills/ams/scripts/run_screener.py --strategy <STRATEGY_NAME> [--pe <MAX_PE>]`
3. **Global Portfolio Ledger**: 
   `python3 ~/.openclaw/skills/ams/scripts/query_portfolio.py [--action <get|add|update|remove>] [--asset <ASSET_NAME>] [--value <VALUE>]`
4. **Dynamic Sentinel Alerts**: 
   To set up persistent alerts, append a monitoring rule (e.g., condition + script invocation) to the file `/root/.openclaw/workspace/HEARTBEAT.md` so the main Agent evaluates it during heartbeat cycles.
```

- **JSON Schema for `query_spread.py` Output**:
```json
{
  "ticker": "159501.SZ",
  "current_price": 1.600,
  "iopv": 1.500,
  "premium_pct": 6.67
}
```

- **JSON Schema for `query_portfolio.py` Output**:
```json
{
  "asset": "159501.SZ",
  "asset_type": "ETF",
  "amount": 500000,
  "cost_basis": 1.200,
  "current_price": 1.600,
  "unrealized_pnl": 200000,
  "profit_pct": 33.33
}
```

- **Disaster Recovery Cron Job Command (Must be executed during deployment)**:
```bash
openclaw cron add --name "ams_ledger_backup" --cron "0 1 * * *" --message "Execute `python3 ~/.openclaw/skills/ams/scripts/backup_ledger.py`. Parse the JSON output, summarize the backup status, and report the daily portfolio snapshot to this channel."
```
