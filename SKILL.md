# Skill Name: AMS (Arbitrage Monitoring System)

## Description
AgentSkill package for Arbitrage Monitoring System. It tracks ETFs and Convertible Bonds for anomalies, checks for restrictions, checks indices, and sends reports.

## Reasoning Protocol (The LLM Brain)
When you receive data from the script, you MUST:
1. Validate if a QDII ETF is "限购" (restricted) using `web_search` if an anomaly involves a QDII ETF.
2. Check overnight index drops (外盘大跌) via `web_search` for context.
3. Use the `message` tool to deliver the final curated report to the Boss (Telegram target `telegram:6228532305`).

## Execution
Run the script via: `python3 scripts/etf_tracker.py`
