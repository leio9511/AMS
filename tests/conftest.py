import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


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
    project_stage_root = REPO_ROOT / ".tmp_path_contract" / tmp_path.name
    data_dir = project_stage_root / "data"
    reports_dir = project_stage_root / "reports"
    data_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    provider_data_path = data_dir / "cb_history_factors_jqdata.csv"
    provider_metrics_path = data_dir / "cb_history_factors_jqdata.metrics.json"
    tushare_data_path = data_dir / "cb_history_factors_tushare.csv"
    tushare_metrics_path = data_dir / "cb_history_factors_tushare.metrics.json"
    config_path = tmp_path / "ams_config.json"

    shutil.copyfile(source_fixture, provider_data_path)
    shutil.copyfile(source_fixture, tushare_data_path)

    relative_data_dir = data_dir.relative_to(REPO_ROOT)
    config_payload = {
        "default_provider": "jqdata",
        "providers": {
            "jqdata": {
                "dataset_path": str(relative_data_dir / "cb_history_factors_jqdata.csv"),
                "metrics_path": str(relative_data_dir / "cb_history_factors_jqdata.metrics.json"),
            },
            "tushare": {
                "dataset_path": str(relative_data_dir / "cb_history_factors_tushare.csv"),
                "metrics_path": str(relative_data_dir / "cb_history_factors_tushare.metrics.json"),
            },
        },
    }
    config_path.write_text(json.dumps(config_payload, indent=2), encoding="utf-8")

    with patch.dict(os.environ, {"AMS_CONFIG_PATH": str(config_path), "AMS_REPORTS_DIR": str(reports_dir)}, clear=False):
        try:
            yield {
                "data": str(provider_data_path),
                "metrics": str(provider_metrics_path),
                "reports": str(reports_dir),
                "config": str(config_path),
                "source_fixture": str(source_fixture),
                "tushare_data": str(tushare_data_path),
                "tushare_metrics": str(tushare_metrics_path),
            }
        finally:
            shutil.rmtree(project_stage_root, ignore_errors=True)
