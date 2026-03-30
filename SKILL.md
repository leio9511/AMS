# Skill Name: AMS (Arbitrage Monitoring System)

## Description
AgentSkill package for Arbitrage Monitoring System. It tracks ETFs and Convertible Bonds for anomalies, checks for restrictions, checks indices, and sends reports.

## Reasoning Protocol (The LLM Brain)
When you receive data from the script, you MUST:
1. Validate if a QDII ETF is "限购" (restricted) using `web_search` if an anomaly involves a QDII ETF.
2. Check overnight index drops (外盘大跌) via `web_search` for context.
3. Deliver the final curated report to the Boss using the native `announce` delivery mechanism (respond directly in the chat, do not use any message tools).
4. CRITICAL SILENCE RULE: If the tracker script outputs no new arbitrage opportunities or anomalies, you MUST reply with exactly and only NO_REPLY. Do not include any pleasantries, summaries, or other text. The entire response must be just the word NO_REPLY.

## Execution
Run the script via: `python3 scripts/etf_tracker.py`
