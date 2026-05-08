import os
import pytest
from pathlib import Path
from ams.utils.path_resolver import (
    resolve_mutable_data_path,
    resolve_runtime_output_path,
    HostLayoutCouplingError,
    get_repo_root
)

def test_precedence_cli_overrides_all(monkeypatch):
    monkeypatch.setenv("AMS_DATA_DIR", "/env/path")
    res = resolve_mutable_data_path(
        default_relative_path="default/data",
        cli_override=Path("/cli/path"),
        env_var="AMS_DATA_DIR",
        config_override="/config/path"
    )
    assert str(res.path) == os.path.abspath("/cli/path")
    assert res.source == "CLI"

def test_precedence_env_overrides_config(monkeypatch):
    monkeypatch.setenv("AMS_DATA_DIR", "/env/path")
    res = resolve_mutable_data_path(
        default_relative_path="default/data",
        cli_override=None,
        env_var="AMS_DATA_DIR",
        config_override="/config/path"
    )
    assert str(res.path) == os.path.abspath("/env/path")
    assert res.source == "ENV"

def test_precedence_project_local_default(monkeypatch):
    monkeypatch.delenv("AMS_DATA_DIR", raising=False)
    res = resolve_mutable_data_path(
        default_relative_path="default/data",
        cli_override=None,
        env_var="AMS_DATA_DIR",
        config_override=None
    )
    assert res.path == (get_repo_root() / "default/data").resolve()
    assert res.source == "DEFAULT"

def test_fail_fast_on_invalid_cli_path(monkeypatch):
    monkeypatch.setenv("AMS_DATA_DIR", "/env/path")
    with pytest.raises(ValueError, match="Invalid path"):
        resolve_mutable_data_path(
            default_relative_path="default/data",
            cli_override="   ",
            env_var="AMS_DATA_DIR",
            config_override="/config/path"
        )

def test_explicit_absolute_override_accepted(monkeypatch):
    monkeypatch.setenv("AMS_DATA_DIR", "/absolute/env/path")
    res = resolve_mutable_data_path(
        default_relative_path="default/data",
        env_var="AMS_DATA_DIR"
    )
    assert str(res.path) == os.path.abspath("/absolute/env/path")
    assert res.source == "ENV"

def test_runtime_output_writable_in_non_root(monkeypatch):
    # Verify that the resolved runtime output paths do not depend on `.openclaw/workspace` or `/root`
    # and properly throws HostLayoutCouplingError if provided.
    with pytest.raises(HostLayoutCouplingError):
        resolve_runtime_output_path(
            default_relative_path="default/out",
            cli_override="/root/projects/AMS/out"
        )
    
    with pytest.raises(HostLayoutCouplingError):
        resolve_runtime_output_path(
            default_relative_path=".openclaw/workspace/out"
        )

    # Valid relative default
    res = resolve_runtime_output_path("valid/out")
    assert res.path == (get_repo_root() / "valid/out").resolve()
    assert res.source == "DEFAULT"
