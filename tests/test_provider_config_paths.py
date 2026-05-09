import json
from pathlib import Path

import pytest

from ams.utils import provider_config
from ams.utils.path_resolver import HostLayoutCouplingError
from ams.utils.provider_config import (
    get_provider_artifact_paths,
    get_repo_root,
    load_provider_config,
    resolve_project_path,
)


def _write_provider_config(config_file: Path, payload: dict) -> None:
    config_file.write_text(json.dumps(payload), encoding="utf-8")


def test_provider_dataset_and_metrics_use_resolver_project_local_defaults(tmp_path, monkeypatch):
    monkeypatch.delenv("AMS_JQDATA_DATASET_PATH", raising=False)
    monkeypatch.delenv("AMS_JQDATA_METRICS_PATH", raising=False)
    repo_root = get_repo_root()
    config_file = tmp_path / "ams_config.json"
    _write_provider_config(
        config_file,
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
        },
    )

    monkeypatch.setenv("AMS_CONFIG_PATH", str(config_file))
    monkeypatch.chdir(tmp_path)

    config_from_tmp_cwd = load_provider_config()
    monkeypatch.chdir(repo_root)
    config_from_repo_cwd = load_provider_config()

    assert config_from_tmp_cwd == config_from_repo_cwd
    assert config_from_tmp_cwd["providers"]["jqdata"]["dataset_path"] == str(repo_root / "data" / "cb_history_factors_jqdata.csv")
    assert config_from_tmp_cwd["providers"]["jqdata"]["metrics_path"] == str(repo_root / "data" / "cb_history_factors_jqdata.metrics.json")
    assert config_from_tmp_cwd["providers"]["tushare"]["dataset_path"] == resolve_project_path("relative", "custom_tushare.csv")
    assert config_from_tmp_cwd["providers"]["tushare"]["metrics_path"] == resolve_project_path("relative", "custom_tushare.metrics.json")


def test_provider_artifact_env_overrides_config_paths(tmp_path, monkeypatch):
    dataset_config_path = tmp_path / "config" / "dataset.csv"
    metrics_config_path = tmp_path / "config" / "metrics.json"
    dataset_env_path = tmp_path / "env" / "dataset.csv"
    metrics_env_path = tmp_path / "env" / "metrics.json"
    config_file = tmp_path / "ams_config.json"
    _write_provider_config(
        config_file,
        {
            "default_provider": "jqdata",
            "providers": {
                "jqdata": {
                    "dataset_path": str(dataset_config_path),
                    "metrics_path": str(metrics_config_path),
                }
            },
        },
    )

    monkeypatch.setenv("AMS_CONFIG_PATH", str(config_file))
    monkeypatch.setenv("AMS_JQDATA_DATASET_PATH", str(dataset_env_path))
    monkeypatch.setenv("AMS_JQDATA_METRICS_PATH", str(metrics_env_path))

    config = load_provider_config()

    assert config["providers"]["jqdata"]["dataset_path"] == str(dataset_env_path)
    assert config["providers"]["jqdata"]["metrics_path"] == str(metrics_env_path)


def test_provider_config_rejects_root_bound_artifact_paths(tmp_path, monkeypatch):
    config_file = tmp_path / "ams_config.json"
    _write_provider_config(
        config_file,
        {
            "default_provider": "jqdata",
            "providers": {
                "jqdata": {
                    "dataset_path": "/root/projects/AMS/data/cb_history_factors_jqdata.csv",
                    "metrics_path": "/root/.openclaw/cb_history_factors_jqdata.metrics.json",
                }
            },
        },
    )

    monkeypatch.setenv("AMS_CONFIG_PATH", str(config_file))

    with pytest.raises(HostLayoutCouplingError):
        load_provider_config()


def test_provider_artifact_env_rejects_openclaw_workspace_dependency(tmp_path, monkeypatch):
    config_file = tmp_path / "ams_config.json"
    _write_provider_config(
        config_file,
        {
            "default_provider": "jqdata",
            "providers": {
                "jqdata": {
                    "dataset_path": "data/cb_history_factors_jqdata.csv",
                    "metrics_path": "data/cb_history_factors_jqdata.metrics.json",
                }
            },
        },
    )

    monkeypatch.setenv("AMS_CONFIG_PATH", str(config_file))
    monkeypatch.setenv("AMS_JQDATA_METRICS_PATH", ".openclaw/workspace/cb.metrics.json")

    with pytest.raises(HostLayoutCouplingError):
        load_provider_config()


def test_load_provider_config_rejects_malformed_json(tmp_path, monkeypatch):
    config_file = tmp_path / "ams_config.json"
    config_file.write_text('{"default_provider": "jqdata",', encoding="utf-8")

    monkeypatch.setenv("AMS_CONFIG_PATH", str(config_file))

    with pytest.raises(ValueError, match="Malformed provider config JSON"):
        load_provider_config()


def test_load_provider_config_rejects_invalid_provider_shape(tmp_path, monkeypatch):
    config_file = tmp_path / "ams_config.json"
    _write_provider_config(
        config_file,
        {
            "default_provider": "jqdata",
            "providers": {
                "jqdata": {
                    "dataset_path": "data/cb_history_factors_jqdata.csv"
                }
            },
        },
    )

    monkeypatch.setenv("AMS_CONFIG_PATH", str(config_file))

    with pytest.raises(ValueError, match="missing required key 'metrics_path'"):
        load_provider_config()


def test_explicit_absolute_provider_path_is_preserved_as_override(tmp_path, monkeypatch):
    dataset_path = tmp_path / "absolute.csv"
    metrics_path = tmp_path / "absolute.metrics.json"
    config_file = tmp_path / "ams_config.json"
    _write_provider_config(
        config_file,
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
        },
    )

    monkeypatch.setenv("AMS_CONFIG_PATH", str(config_file))

    config = load_provider_config()

    assert config["default_provider"] == "tushare"
    assert get_provider_artifact_paths("tushare", config=config)["dataset_path"] == str(dataset_path)
    assert get_provider_artifact_paths("tushare", config=config)["metrics_path"] == str(metrics_path)
