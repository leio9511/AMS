import json
import os
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

import etl.jqdata_sync_cb as jq_sync
from ams.utils.path_resolver import get_repo_root, HostLayoutCouplingError
from etl.jqdata_sync_cb import audit_cb_data, sync_cb_data


def _write_provider_config(config_file: Path, dataset_path: Path, metrics_path: Path) -> None:
    config_payload = {
        "default_provider": "jqdata",
        "providers": {
            "jqdata": {
                "dataset_path": str(dataset_path),
                "metrics_path": str(metrics_path),
            }
        },
    }
    config_file.write_text(json.dumps(config_payload, indent=2), encoding="utf-8")


@pytest.fixture
def jqdata_success_mock():
    with patch("etl.jqdata_sync_cb.jqdatasdk") as mock_jqdata, \
         patch("ams.validators.cb_data_validator.DatasetSemanticValidator") as mock_semantic_validator, \
         patch("ams.validators.cb_data_validator.CBDataValidator") as mock_validator:
        mock_semantic_validator.return_value.validate_dataframe.return_value = True
        mock_validator.return_value.validate_dataframe.return_value = True
        mock_jqdata.auth.return_value = None
        mock_jqdata.get_all_securities.return_value = pd.DataFrame(
            {"code": ["110059.XSHG"]},
            index=["110059.XSHG"],
        )
        mock_jqdata.get_price.return_value = pd.DataFrame(
            {
                "time": ["2020-01-02"],
                "code": ["110059.XSHG"],
                "open": [100.0],
                "high": [101.0],
                "low": [99.0],
                "close": [100.5],
                "volume": [1000],
            }
        ).set_index(["time", "code"])
        mock_jqdata.get_extras.return_value = pd.DataFrame(
            {"000001.XSHE": [False]},
            index=pd.to_datetime(["2020-01-02"]),
        )
        mock_jqdata.get_security_info.side_effect = AssertionError("legacy get_security_info path must not be used")
        mock_jqdata.finance.run_query.side_effect = AssertionError("finance.CCB_CALL must not be queried")
        mock_jqdata.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
        mock_jqdata.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
        mock_jqdata.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True
        mock_jqdata.bond.run_query.side_effect = [
            pd.DataFrame(
                {
                    "code": ["110059"],
                    "company_code": ["000001.XSHE"],
                    "delist_Date": ["2025-12-31"],
                }
            ),
            pd.DataFrame(
                {
                    "date": ["2020-01-02"],
                    "code": ["110059"],
                    "exchange_code": ["XSHG"],
                    "convert_premium_rate": [10.0],
                }
            ),
        ]
        yield mock_jqdata


def test_jqdata_sync_defaults_resolve_from_provider_config_not_root_constants(tmp_path, monkeypatch, jqdata_success_mock):
    dataset_path = tmp_path / "artifacts" / "cb_history_factors_jqdata.csv"
    metrics_path = tmp_path / "artifacts" / "cb_history_factors_jqdata.metrics.json"
    config_path = tmp_path / "ams_config.json"
    _write_provider_config(config_path, dataset_path, metrics_path)

    monkeypatch.setenv("AMS_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("JQDATA_USER", "test_user")
    monkeypatch.setenv("JQDATA_PWD", "test_password")
    monkeypatch.setattr(jq_sync, "DATA_PATH", jq_sync._DEFAULT_DATA_PATH)
    monkeypatch.setattr(jq_sync, "METRICS_PATH", jq_sync._DEFAULT_METRICS_PATH)

    forbidden_root = "/root/" + "projects/AMS"
    assert forbidden_root not in jq_sync.DATA_PATH
    assert forbidden_root not in jq_sync.METRICS_PATH

    sync_cb_data(start_date="2020-01-02", end_date="2020-01-02")

    assert dataset_path.exists()
    assert metrics_path.exists()


def test_jqdata_audit_report_uses_runtime_output_contract(tmp_path, monkeypatch, jqdata_success_mock):
    dataset_path = tmp_path / "artifacts" / "cb_history_factors_jqdata.csv"
    metrics_path = tmp_path / "artifacts" / "cb_history_factors_jqdata.metrics.json"
    reports_dir = tmp_path / "contract_reports"
    config_path = tmp_path / "ams_config.json"
    _write_provider_config(config_path, dataset_path, metrics_path)

    monkeypatch.setenv("AMS_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("AMS_REPORTS_DIR", str(reports_dir))
    monkeypatch.setenv("JQDATA_USER", "test_user")
    monkeypatch.setenv("JQDATA_PWD", "test_password")

    report_path = audit_cb_data(start_date="2020-01-02", end_date="2020-01-02")

    assert Path(report_path).parent == reports_dir
    assert Path(report_path).exists()
    forbidden_workspace = ".openclaw/" + "workspace"
    assert forbidden_workspace not in report_path

    mock = jqdata_success_mock
    mock.bond.run_query.side_effect = [
        pd.DataFrame({"code": ["110059"], "company_code": ["000001.XSHE"], "delist_Date": ["2025-12-31"]}),
        pd.DataFrame({"date": ["2020-01-02"], "code": ["110059"], "exchange_code": ["XSHG"], "convert_premium_rate": [10.0]}),
    ]
    monkeypatch.delenv("AMS_REPORTS_DIR")

    default_report_path = audit_cb_data(start_date="2020-01-02", end_date="2020-01-02")
    assert Path(default_report_path).parent == get_repo_root() / "reports"
    assert forbidden_workspace not in default_report_path


@pytest.mark.parametrize(
    "dataset_path,metrics_path",
    [
        (("/root/" + "projects/AMS/data/cb.csv"), None),
        (None, ("/root/" + ".openclaw/cb.metrics.json")),
        ((".openclaw/" + "workspace/cb.csv"), None),
        (None, ("some/.openclaw/" + "workspace/cb.metrics.json")),
    ],
)
def test_etl_rejects_root_bound_dataset_and_metrics_overrides(tmp_path, monkeypatch, dataset_path, metrics_path):
    config_path = tmp_path / "ams_config.json"
    _write_provider_config(
        config_path,
        tmp_path / "safe" / "cb_history_factors_jqdata.csv",
        tmp_path / "safe" / "cb_history_factors_jqdata.metrics.json",
    )
    monkeypatch.setenv("AMS_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("JQDATA_USER", "test_user")
    monkeypatch.setenv("JQDATA_PWD", "test_password")

    from etl.cb_etl_runner import run_etl

    with pytest.raises(HostLayoutCouplingError):
        run_etl(
            "2020-01-02",
            "2020-01-02",
            "jqdata",
            promote=True,
            dataset_path=dataset_path,
            metrics_path=metrics_path,
        )
