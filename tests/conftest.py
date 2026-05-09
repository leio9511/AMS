import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from ams.utils.path_resolver import resolve_repo_asset


def repo_asset(relative_path: str | Path) -> Path:
    return resolve_repo_asset(relative_path)


@pytest.fixture
def fixture_asset():
    def _resolve(filename: str) -> Path:
        return resolve_repo_asset(Path("tests/fixtures") / filename)

    return _resolve


@pytest.fixture
def golden_asset():
    def _resolve(relative_path: str | Path) -> Path:
        return resolve_repo_asset(Path("tests/golden") / relative_path)

    return _resolve


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
        with patch.dict(os.environ, {"AMS_JQDATA_DATASET_PATH": data_path, "AMS_JQDATA_METRICS_PATH": metrics_path}):
            yield
@pytest.fixture
def isolated_paths(tmp_path):
    source_fixture = repo_asset("tests/fixtures/cb_history_factors.csv")
    project_stage_root = tmp_path / "path-contract"
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
    provider_metrics_path.write_text("{}\n", encoding="utf-8")
    tushare_metrics_path.write_text("{}\n", encoding="utf-8")

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

    isolated_env = {
        "AMS_CONFIG_PATH": str(config_path),
        "AMS_REPORTS_DIR": str(reports_dir),
    }

    clean_env = os.environ.copy()
    for k in list(clean_env.keys()):
        if k.startswith("AMS_"):
            del clean_env[k]
    clean_env.update(isolated_env)

    with patch.dict(os.environ, clean_env, clear=True):
        yield {
            "data": str(provider_data_path),
            "default_data": str(provider_data_path),
            "metrics": str(provider_metrics_path),
            "default_metrics": str(provider_metrics_path),
            "reports": str(reports_dir),
            "config": str(config_path),
            "env": clean_env.copy(),
            "source_fixture": str(source_fixture),
            "tushare_data": str(tushare_data_path),
            "tushare_metrics": str(tushare_metrics_path),
        }
