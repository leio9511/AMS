# PR-001: AMS Daemon Revival and Process Management

## Goal
Fix the AMS reporting failure by ensuring `etf_tracker.py` is robustly managed via a resilient process manager (like systemd) or converted to stateless cron jobs, and ensure it passes preflight syntax checks.

## Scope
- `etf_tracker.py`
- Setup script for systemd or cron (e.g., `setup_service.sh` or `ams_cron.sh`)

## Contracts
- Market reports must fire at pre-market (09:25), mid-market, and post-market (15:05).
- Output format must remain Markdown-compatible for Telegram.

## Acceptance Criteria (AC)
1. `etf_tracker.py` compiles without syntax errors (`python3 -m py_compile etf_tracker.py`).
2. A bash script (`install_daemon.sh` or `setup_cron.sh`) is provided to install the daemon as a systemd service (so it auto-restarts on crash or reboot) OR registers a strict cron schedule.
3. The script handles API timeouts gracefully without crashing the main loop.

## Anti-Patterns (尸检报告/避坑指南)
- **DO NOT** rely on `nohup python3 etf_tracker.py &` running in a volatile terminal session. It will die.
- **DO NOT** rewrite the core data parsing logic; focus ONLY on the scheduling/daemonization stability.
