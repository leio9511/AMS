---
name: ams
description: Automated Market Screener & Global Portfolio Ledger. Use this skill to query ETF/CB premiums, screen A-share stocks (e.g. Crystal Fly), manage the global portfolio ledger, and set up dynamic sentinel alerts.
---

# AMS AgentSkill

# AMS Runbook & Governance 
**MANDATORY:** Currently in DEVELOPMENT stage. All invocations MUST use the workspace path: `/root/projects/AMS/`. DO NOT use runtime paths until the stage is switched to PRODUCTION. 

You are equipped with the AMS toolset. To answer questions about market data or portfolios, strictly use the `exec` tool to run the following Python pipes and interpret their JSON output.

1. **Market Spread Radar**: 
   `python3 ~/.openclaw/skills/ams/scripts/query_spread.py --ticker <TICKER>`
2. **On-demand Screener**: 
   `python3 ~/.openclaw/skills/ams/scripts/run_screener.py --strategy <STRATEGY_NAME> [--pe <MAX_PE>]`
3. **Global Portfolio Ledger**: 
   `python3 ~/.openclaw/skills/ams/scripts/query_portfolio.py [--action <get|add|update|remove>] [--asset <ASSET_NAME>] [--value <VALUE>]`
4. **Dynamic Sentinel Alerts**: 
   To set up persistent alerts, append a monitoring rule (e.g., condition + script invocation) to the file `/root/.openclaw/workspace/HEARTBEAT.md` so the main Agent evaluates it during heartbeat cycles.
5. **Strategy Backtester**:
   `python3 main_runner.py --strategy <ID> --start-date <YYYY-MM-DD> --end-date <YYYY-MM-DD> --capital <FLOAT> --top-n <INT> --rebalance <daily|weekly> --tp-mode <both|position|intraday> --tp-pos <FLOAT> --tp-intra <FLOAT> --sl <FLOAT> [--format json]`
   Use this for rigorous strategy validation. Use `--format json` for bit-accurate results.
