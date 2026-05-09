import pytest
import os
import json
import pandas as pd
from unittest.mock import patch
import sys

# Add root to sys.path to ensure imports work if running from tests/
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from etl.cb_etl_runner import run_etl, get_provider
import ams.utils.provider_config

@pytest.fixture
def temp_config(tmp_path):
    config_file = tmp_path / "ams_config.json"
    config_data = {
        "default_provider": "tushare",
        "providers": {
            "jqdata": {
                "dataset_path": str(tmp_path / "cb_history_factors_jqdata.csv"),
                "metrics_path": str(tmp_path / "cb_history_factors_jqdata.metrics.json")
            },
            "tushare": {
                "dataset_path": str(tmp_path / "cb_history_factors_tushare.csv"),
                "metrics_path": str(tmp_path / "cb_history_factors_tushare.metrics.json")
            }
        }
    }
    with open(config_file, "w") as f:
        json.dump(config_data, f)

    with patch("ams.utils.provider_config.DEFAULT_CONFIG_PATH", str(config_file)):
        yield config_data


def test_config_precedence(temp_config):
    if "AMS_JQDATA_DATASET_PATH" in os.environ: del os.environ["AMS_JQDATA_DATASET_PATH"]
    if "AMS_JQDATA_METRICS_PATH" in os.environ: del os.environ["AMS_JQDATA_METRICS_PATH"]
    # Verify that CLI (or explicit call) overrides config default
    with patch("etl.cb_etl_runner.get_provider") as mock_get_provider:
        with patch("etl.cb_etl_runner.CBETLPipeline") as mock_pipeline_cls:
            mock_pipeline = mock_pipeline_cls.return_value
            mock_pipeline.run_stage_a_source_acquisition.return_value = True
            mock_pipeline.run_stage_b_supportability_classification.return_value = True
            mock_pipeline.run_stage_f_validator.return_value = True
            mock_pipeline.get_final_report.return_value = {"status": "ok"}

            # Mock df with all canonical columns
            mock_pipeline.df = pd.DataFrame({
                "ticker": ["123456.SH"],
                "date": ["2025-01-01"],
                "open": [100.0],
                "high": [105.0],
                "low": [95.0],
                "close": [102.0],
                "volume": [1000],
                "premium_rate": [10.0],
                "double_low": [112.0],
                "underlying_ticker": ["000001.SZ"],
                "is_st": [False],
                "is_redeemed": [False],
                "supportability_bucket": ["supportable"],
                "bond_code_raw": ["123456"]
            })
            mock_pipeline.results = {
                "source_coverage": {},
                "premium_join_summary": {},
                "redemption_summary": {},
                "validator_summary": {}
            }

            # Explicitly choose jqdata, even though default is tushare.
            # The refactor must keep the normalized config shape compatible with
            # the existing runtime consumer logic in cb_etl_runner.
            jq_path = temp_config["providers"]["jqdata"]["dataset_path"]
            run_etl("2025-01-01", "2025-01-02", "jqdata", promote=True)

            assert os.path.exists(jq_path)
            assert not os.path.exists(temp_config["providers"]["tushare"]["dataset_path"])
            mock_get_provider.assert_called_once_with("jqdata", jqdata_client=None)


def test_runner_provider_selection():
    with patch("etl.cb_etl_runner.TuShareProvider") as mock_tushare:
        with patch.dict(os.environ, {"TUSHARE_TOKEN": "test_token"}):
            get_provider("tushare")
            mock_tushare.assert_called()


def test_main_runner_datasource_selection(temp_config):
    import main_runner

    test_args = [
        "main_runner.py",
        "--strategy", "cb_rotation",
        "--start-date", "2025-01-01",
        "--end-date", "2025-01-02",
        "--capital", "1000000",
        "--top-n", "10",
        "--rebalance", "weekly",
        "--tp-mode", "position",
        "--tp-pos", "0.2",
        "--sl", "-0.1",
        "--data-source", "tushare"
    ]

    with patch.object(sys, "argv", test_args):
        with patch("main_runner.HistoryDataFeed") as mock_feed:
            with patch("main_runner.BacktestRunner.run") as mock_run:
                mock_run.return_value = pd.DataFrame()
                with patch("main_runner.reporting.generate_report_data"):
                    main_runner.main()
                    # main_runner should keep consuming the normalized provider
                    # config output without requiring a direct helper migration in
                    # this slice.
                    expected_path = temp_config["providers"]["tushare"]["dataset_path"]
                    mock_feed.assert_called_once_with(file_path=expected_path)


def test_provider_provenance(temp_config):
    if "AMS_JQDATA_DATASET_PATH" in os.environ: del os.environ["AMS_JQDATA_DATASET_PATH"]
    if "AMS_JQDATA_METRICS_PATH" in os.environ: del os.environ["AMS_JQDATA_METRICS_PATH"]
    # Verify that running for both results in two distinct files
    with patch("etl.cb_etl_runner.get_provider"):
        with patch("etl.cb_etl_runner.CBETLPipeline") as mock_pipeline_cls:
            mock_pipeline = mock_pipeline_cls.return_value
            mock_pipeline.run_stage_a_source_acquisition.return_value = True
            mock_pipeline.run_stage_b_supportability_classification.return_value = True
            mock_pipeline.run_stage_f_validator.return_value = True
            mock_pipeline.get_final_report.return_value = {"status": "ok"}

            mock_pipeline.df = pd.DataFrame({
                "ticker": ["123456.SH"],
                "date": ["2025-01-01"],
                "open": [100.0],
                "high": [105.0],
                "low": [95.0],
                "close": [102.0],
                "volume": [1000],
                "premium_rate": [10.0],
                "double_low": [112.0],
                "underlying_ticker": ["000001.SZ"],
                "is_st": [False],
                "is_redeemed": [False],
                "supportability_bucket": ["supportable"],
                "bond_code_raw": ["123456"]
            })
            mock_pipeline.results = {
                "source_coverage": {},
                "premium_join_summary": {},
                "redemption_summary": {},
                "validator_summary": {}
            }

            jq_path = temp_config["providers"]["jqdata"]["dataset_path"]
            ts_path = temp_config["providers"]["tushare"]["dataset_path"]

            run_etl("2025-01-01", "2025-01-02", "jqdata", promote=True)
            run_etl("2025-01-01", "2025-01-02", "tushare", promote=True)

            assert os.path.exists(jq_path)
            assert os.path.exists(ts_path)
            assert jq_path != ts_path
