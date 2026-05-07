import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def mock_dataset_semantic_validator():
    with patch("ams.validators.cb_data_validator.DatasetSemanticValidator") as mock_validator:
        mock_validator.return_value.validate_dataframe.return_value = True
        yield mock_validator


@pytest.fixture(autouse=True)
def mock_dataset_paths():
    with tempfile.TemporaryDirectory() as tmpdir:
        data_path = os.path.join(tmpdir, "cb_history_factors.csv")
        metrics_path = os.path.join(tmpdir, "cb_history_factors.metrics.json")
        with patch("etl.jqdata_sync_cb.DATA_PATH", data_path), \
             patch("etl.jqdata_sync_cb.METRICS_PATH", metrics_path):
            yield


@pytest.fixture
def isolated_paths(tmp_path):
    source_fixture = Path(__file__).resolve().parent / "fixtures" / "cb_history_factors.csv"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()

    provider_data_path = data_dir / "cb_history_factors_jqdata.csv"
    provider_metrics_path = data_dir / "cb_history_factors_jqdata.metrics.json"
    tushare_data_path = data_dir / "cb_history_factors_tushare.csv"
    tushare_metrics_path = data_dir / "cb_history_factors_tushare.metrics.json"
    config_path = tmp_path / "ams_config.json"

    shutil.copyfile(source_fixture, provider_data_path)
    shutil.copyfile(source_fixture, tushare_data_path)

    config_payload = {
        "default_provider": "jqdata",
        "providers": {
            "jqdata": {
                "dataset_path": str(provider_data_path),
                "metrics_path": str(provider_metrics_path),
            },
            "tushare": {
                "dataset_path": str(tushare_data_path),
                "metrics_path": str(tushare_metrics_path),
            },
        },
    }
    config_path.write_text(json.dumps(config_payload, indent=2), encoding="utf-8")

    original_join = os.path.join
    original_makedirs = os.makedirs

    def mock_join(base, *parts):
        if isinstance(base, str) and base == "/root/projects/AMS/reports":
            return original_join(str(reports_dir), *parts)
        return original_join(base, *parts)

    def mock_makedirs(path, *args, **kwargs):
        if path == "/root/projects/AMS/reports":
            return original_makedirs(str(reports_dir), *args, **kwargs)
        return original_makedirs(path, *args, **kwargs)

    with patch.dict(os.environ, {"AMS_CONFIG_PATH": str(config_path)}, clear=False), \
         patch("ams.utils.provider_config.DEFAULT_CONFIG_PATH", config_path), \
         patch("etl.jqdata_sync_cb.DATA_PATH", str(provider_data_path)), \
         patch("etl.jqdata_sync_cb.METRICS_PATH", str(provider_metrics_path)), \
         patch("etl.cb_etl_runner.os.path.join", side_effect=mock_join), \
         patch("etl.cb_etl_runner.os.makedirs", side_effect=mock_makedirs):
        yield {
            "data": str(provider_data_path),
            "metrics": str(provider_metrics_path),
            "reports": str(reports_dir),
            "config": str(config_path),
            "source_fixture": str(source_fixture),
            "tushare_data": str(tushare_data_path),
            "tushare_metrics": str(tushare_metrics_path),
        }
