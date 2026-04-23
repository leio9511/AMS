# Walk-Forward Analysis Design

## 1. Overview
Walk-Forward Analysis (WFA) is a method used in finance to determine the robustness of a trading strategy. It involves optimizing parameters on a training (in-sample) period and then testing those parameters on a following testing (out-of-sample) period. This process is "walked forward" through time.

## 2. Design Goals for AMS
The future Walk-Forward system in AMS will aim to:
- Automate the slicing of historical data into multiple In-Sample (IS) and Out-of-Sample (OOS) windows.
- Execute parameter optimization (e.g., Grid Search or Genetic Algorithm) on IS windows.
- Validate optimized parameters on OOS windows to detect over-fitting.
- Provide a "Walk-Forward Efficiency" metric.

## 3. Integration with Validation Framework
Walk-Forward Analysis will be Layer 5 of the Validation Framework, building upon the foundations of:
1. **Smoke**: Ensuring CLI path works.
2. **Golden Regression**: Ensuring no drift in known cases.
3. **Sensitivity Sanity**: Ensuring parameters remain influential.
4. **Canonical Path Consistency**: Ensuring data path parity.
5. **Walk-Forward**: Ensuring strategy robustness across time.

## 4. Expansion Placeholders
The following placeholders are established for future development:

### 4.1 Suite Location
`tests/validation/test_walk_forward.py`
This file will contain the test suite for automated walk-forward gates.

### 4.2 Artifacts Directory
`tests/golden/walk_forward/`
This directory will store frozen IS/OOS window definitions and their expected efficiency results.

### 4.3 Engine Extension
`ams/runners/walk_forward_runner.py`
A specialized runner to handle multiple backtest iterations and parameter aggregation.

## 5. Implementation Roadmap
1. Define sliding window schema (e.g., 6 months IS, 2 months OOS).
2. Implement `WalkForwardRunner`.
3. Create baseline robustness metrics (Calmar consistency, Profit Factor stability).
4. Integrate with `preflight.sh` as a high-level gate.
