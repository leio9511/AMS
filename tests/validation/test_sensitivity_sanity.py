import json
from copy import deepcopy
from decimal import Decimal

import pytest

from ams.core.cb_rotation_strategy import CBRotationStrategy
from ams.core.factory import StrategyFactory
from ams.core.history_datafeed import HistoryDataFeed
from ams.core.sim_broker import SimBroker
from ams.models.config import TakeProfitConfig, TakeProfitMode
from ams.runners.backtest_runner import BacktestRunner
from ams.utils import reporting
from ams.utils.path_resolver import resolve_repo_asset


SUMMARY_METRICS = (
    "final_equity",
    "total_return",
    "max_drawdown",
    "calmar_ratio",
)
SENSITIVITY_CASE_KEY = "CASE_WEEKLY_BEST"
GOLDEN_CASES_FILE = resolve_repo_asset("tests/golden/baselines/golden_cases.json")
GOLDEN_DATA_PATH = resolve_repo_asset("tests/golden/data/cb_history_factors_golden_2025_2026.csv")


def _ensure_strategy_registered():
    StrategyFactory.register_strategy("cb_rotation")(CBRotationStrategy)


def _load_golden_case(case_key: str = SENSITIVITY_CASE_KEY):
    if not GOLDEN_CASES_FILE.exists():
        pytest.skip(f"Golden cases file not found: {GOLDEN_CASES_FILE}")

    data = json.loads(GOLDEN_CASES_FILE.read_text(encoding="utf-8"))
    case = data.get(case_key)
    assert case is not None, f"{case_key} not found in golden_cases.json"
    return case


def _build_take_profit_config(params):
    tp_mode = params.get("tp_mode")
    if tp_mode is None:
        return None

    mode = TakeProfitMode(tp_mode)
    pos_threshold = params.get("tp_pos")
    intra_threshold = params.get("tp_intra")

    if mode == TakeProfitMode.BOTH and (pos_threshold is None or intra_threshold is None):
        raise ValueError(f"ERROR: --tp-mode '{tp_mode}' requires both --tp-pos and --tp-intra to be set.")

    return TakeProfitConfig(
        mode=mode,
        pos_threshold=Decimal(str(pos_threshold)) if pos_threshold is not None else None,
        intra_threshold=Decimal(str(intra_threshold)) if intra_threshold is not None else None,
    )


def _run_backtest_in_process(params, golden_market_data):
    _ensure_strategy_registered()

    data_feed = HistoryDataFeed(data=golden_market_data)
    broker = SimBroker(initial_cash=params["capital"])
    strategy = StrategyFactory.create_strategy(
        params["strategy"],
        top_n=params["top_n"],
        rebalance_period=params["rebalance"],
        stop_loss_threshold=params["sl"],
        tp_mode=params["tp_mode"],
        tp_config=_build_take_profit_config(params),
    )
    runner = BacktestRunner(data_feed, broker, strategy)
    equity_curve = runner.run(params["start_date"], params["end_date"])
    return reporting.generate_report_data(equity_curve, params["capital"])


def _summary_changed(before_summary, after_summary):
    return any(str(before_summary[metric]) != str(after_summary[metric]) for metric in SUMMARY_METRICS)


def _describe_summary_comparison(before_summary, after_summary):
    return "; ".join(
        f"{metric}: {before_summary[metric]} -> {after_summary[metric]}"
        for metric in SUMMARY_METRICS
    )


@pytest.fixture(scope="module")
def baseline_case():
    # Shared baseline config path and case loading for the sensitivity matrix.
    return _load_golden_case()


@pytest.fixture(scope="module")
def golden_market_data():
    if not GOLDEN_DATA_PATH.exists():
        pytest.skip(f"Golden data file not found: {GOLDEN_DATA_PATH}")

    # Load the repo-owned golden dataset once, then hand each run a fresh feed copy.
    return HistoryDataFeed(file_path=str(GOLDEN_DATA_PATH)).data.copy()


@pytest.fixture(scope="module")
def baseline_summary(baseline_case, golden_market_data):
    # Execute the golden baseline exactly once and reuse the summary across all perturbations.
    return _run_backtest_in_process(baseline_case, golden_market_data)["summary"]


@pytest.mark.parametrize(
    ("parameter_name", "perturbed_value"),
    [("sl", -0.05), ("tp_pos", 0.25), ("tp_intra", 0.08)],
    ids=["sl--0.05", "tp_pos-0.25", "tp_intra-0.08"],
)
def test_sensitivity_dimension_changes_summary(
    parameter_name,
    perturbed_value,
    baseline_case,
    baseline_summary,
    golden_market_data,
):
    perturbed_params = deepcopy(baseline_case)
    original_value = perturbed_params[parameter_name]
    perturbed_params[parameter_name] = perturbed_value

    perturbed_summary = _run_backtest_in_process(perturbed_params, golden_market_data)["summary"]

    assert _summary_changed(baseline_summary, perturbed_summary), (
        f"Sensitivity failure: summary remained identical when {parameter_name} was modified "
        f"from {original_value} to {perturbed_value}. "
        f"Baseline vs perturbed: {_describe_summary_comparison(baseline_summary, perturbed_summary)}"
    )


def test_summary_difference_helper_only_flags_real_changes():
    summary_a = {
        "final_equity": "5160304.1",
        "total_return": "0.290076025",
        "max_drawdown": "-0.03358338309209775",
        "calmar_ratio": "8.637486705985126892185289367",
    }
    summary_b = summary_a.copy()

    assert not _summary_changed(summary_a, summary_b), (
        "Identical summaries should NOT be marked as different"
    )

    summary_c = summary_a.copy()
    summary_c["final_equity"] = "5160304.2"

    assert _summary_changed(summary_a, summary_c), (
        "Summaries with one different metric SHOULD be marked as different"
    )
