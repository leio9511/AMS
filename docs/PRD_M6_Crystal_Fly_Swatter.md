# PRD: M6 - "Crystal Fly Swatter" Value Stock Screener

## 1. Vision & Goal
To implement a sophisticated, multi-layered value stock screening strategy based on the "Crystal Fly Swatter" philosophy. This tool will automatically identify deeply undervalued, high-quality companies in the A-share market that are poised for a potential turnaround, and present them as a curated list in the daily closing report.

## 2. Architecture: Data-Reasoning Decoupling
This feature MUST follow the "Lobster Architecture" principle of separating data from reasoning.
- **Data Layer (The Script)**: A new Python script (`scripts/crystal_fly_swatter.py`) will act as a pure data filter. It connects to a financial data source, applies a strict 6-layer filtering funnel, and outputs a JSON list of qualifying stock codes to stdout. It performs no analysis.
- **Reasoning Layer (The Agent Skill)**: The `ams` skill (`SKILL.md`) will be updated. When the Manager (Qbot) receives the JSON list from the script, it will perform qualitative analysis (e.g., via `web_search` for recent negative news) on each stock before synthesizing a human-readable report for the Boss.

## 3. Core Feature: The 6-Layer Filtering Funnel
The script must implement the following sequential filters:

### Layer 0: Data Acquisition
- **Requirement**: Find and integrate a data source (e.g., Tushare, AkShare) that provides the necessary fields for all A-share stocks.
- **Required Fields**: YTD Return, PE/PB History, Forward PE (e.g., 2026), Net Profit Growth Forecast, Balance Sheet metrics, Cash Flow metrics, Industry classification.

### Layer 1: Growth Gate (Mandatory)
- **Rule**: "今年业绩增长好" (Good earnings growth this year).
- **Quantification**: `Forward Net Profit Growth > 20%`.

### Layer 2: Health Gate (Mandatory)
- **Rule**: "资产负债表和现金流全市场顶尖" (Top-tier balance sheet and cash flow).
- **Quantification**: Must satisfy all:
  - `Operating Cash Flow > 0`
  - `Current Ratio > 2`
  - `Debt-to-Asset Ratio < 60%`

### Layer 3: Valuation Gate
- **Rule**: "深度熊市估值" (Deep bear market valuation).
- **Quantification**: Must satisfy both:
  - `Forward PE <= 20` (Adjusted from 15)
  - `PE-TTM Historical Percentile < 20%`

### Layer 4: Contrarian Gate
- **Rule**: "今年大跌" (Significant drop this year).
- **Quantification**: `Year-to-Date Return < -15%`.

### Layer 5: Macro Gate
- **Rule**: "与石油危机无关甚至受益于通胀的标的" (Immune to oil crisis / benefits from inflation).
- **Quantification**:
  - **Exclude**: Airlines, Shipping, cost-sensitive manufacturing.
  - **Include/Favor**: Energy (Oil, Coal), Agriculture, Essential Consumer Goods.

### Layer 6: Final Selection
- **Rule**: After passing the mandatory Layer 1 and Layer 2, a stock must satisfy **at least two** of the criteria from Layers 3, 4, and 5.

## 4. Integration
The output of this screener will be integrated into the `--mode=closing` report of the main `etf_tracker.py` script.

## 5. Acceptance Criteria (for the entire Milestone)
- A reliable data source for A-share financials is successfully integrated.
- The `crystal_fly_swatter.py` script correctly filters stocks according to the 6-layer funnel.
- The final closing report includes a new section with the curated list and the LLM's qualitative analysis.
