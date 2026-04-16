# AMS (Automated Market Screener) v2.0

AMS is an event-driven, micro-quantitative trading framework built for the OpenClaw ecosystem. It is designed to rigorously separate pure strategy logic from data acquisition and execution mechanics.

## 🌟 The Vision: "Write Once, Run Anywhere"
The core philosophy of AMS v2.0 is to eliminate the drift between backtesting and live trading. By utilizing an **Event-Driven Architecture (EDA)** and **Dependency Injection**:
- You write your trading strategy **once**.
- In **Backtesting**: You plug in historical data feeds and a simulated broker.
- In **Live Trading**: You plug in real-time QMT data feeds and a live QMT broker.
- **Zero code changes** are required in the strategy itself to switch environments.

## 🚀 Quick Start

**1. Install Dependencies**
```bash
pip install -r requirements.txt
```

**2. Run a Backtest**
```bash
python scripts/main_runner.py  # Or specific runner in ams/runners/
```

## 📚 Documentation
To understand how to build upon AMS, please read the following core documents before contributing:
1. [Architecture & Methodology](docs/architecture/ARCHITECTURE.md): Learn about the "CD Player Pattern" and Data Contracts.
2. [Best Practices & Rules](BEST_PRACTICES.md): The absolute engineering laws of this repository (Import rules, data safety, etc.).