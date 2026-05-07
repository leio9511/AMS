import json
from pathlib import Path

import pytest

from ams.utils import provider_config
from ams.utils.provider_config import (
    get_provider_artifact_paths,
    get_repo_root,
    load_provider_config,
    resolve_project_path,
)


def test_project_local_defaults_are_repo_root_anchored(tmp_path):
    repo_root = get_repo_root()
    config_file = tmp_path / "ams_config.json"
    config_file.write_text(
        json.dumps(
            {
                "default_provider": "jqdata",
                "providers": {
                    "jqdata": {
                        "dataset_path": "data/cb_history_factors_jqdata.csv",
                        "metrics_path": "data/cb_history_factors_jqdata.metrics.json",
                    },
                    "tushare": {
                        "dataset_path": "relative/custom_tushare.csv",
                        "metrics_path": "relative/custom_tushare.metrics.json",
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    original_path = provider_config.DEFAULT_CONFIG_PATH
    provider_config.DEFAULT_CONFIG_PATH = config_file
    try:
        config = load_provider_config()
    finally:
        provider_config.DEFAULT_CONFIG_PATH = original_path

    assert config["providers"]["jqdata"]["dataset_path"] == str(repo_root / "data" / "cb_history_factors_jqdata.csv")
    assert config["providers"]["jqdata"]["metrics_path"] == str(repo_root / "data" / "cb_history_factors_jqdata.metrics.json")
    assert config["providers"]["tushare"]["dataset_path"] == resolve_project_path("relative", "custom_tushare.csv")
    assert config["providers"]["tushare"]["metrics_path"] == resolve_project_path("relative", "custom_tushare.metrics.json")


def test_load_provider_config_rejects_malformed_json(tmp_path):
    config_file = tmp_path / "ams_config.json"
    config_file.write_text('{"default_provider": "jqdata",', encoding="utf-8")

    original_path = provider_config.DEFAULT_CONFIG_PATH
    provider_config.DEFAULT_CONFIG_PATH = config_file
    try:
        with pytest.raises(ValueError, match="Malformed provider config JSON"):
            load_provider_config()
    finally:
        provider_config.DEFAULT_CONFIG_PATH = original_path


def test_load_provider_config_rejects_invalid_provider_shape(tmp_path):
    config_file = tmp_path / "ams_config.json"
    config_file.write_text(
        json.dumps(
            {
                "default_provider": "jqdata",
                "providers": {
                    "jqdata": {
                        "dataset_path": "data/cb_history_factors_jqdata.csv"
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    original_path = provider_config.DEFAULT_CONFIG_PATH
    provider_config.DEFAULT_CONFIG_PATH = config_file
    try:
        with pytest.raises(ValueError, match="missing required key 'metrics_path'"):
            load_provider_config()
    finally:
        provider_config.DEFAULT_CONFIG_PATH = original_path


def test_explicit_absolute_provider_path_is_preserved_as_override(tmp_path):
    dataset_path = tmp_path / "absolute.csv"
    metrics_path = tmp_path / "absolute.metrics.json"
    config_file = tmp_path / "ams_config.json"
    config_file.write_text(
        json.dumps(
            {
                "default_provider": "tushare",
                "providers": {
                    "jqdata": {
                        "dataset_path": "data/cb_history_factors_jqdata.csv",
                        "metrics_path": "data/cb_history_factors_jqdata.metrics.json",
                    },
                    "tushare": {
                        "dataset_path": str(dataset_path),
                        "metrics_path": str(metrics_path),
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    original_path = provider_config.DEFAULT_CONFIG_PATH
    provider_config.DEFAULT_CONFIG_PATH = config_file
    try:
        config = load_provider_config()
    finally:
        provider_config.DEFAULT_CONFIG_PATH = original_path

    assert config["default_provider"] == "tushare"
    assert get_provider_artifact_paths("tushare", config=config)["dataset_path"] == str(dataset_path)
    assert get_provider_artifact_paths("tushare", config=config)["metrics_path"] == str(metrics_path)
