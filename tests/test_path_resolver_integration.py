import os
import pytest
from pathlib import Path
from ams.utils.path_resolver import resolve_mutable_data_path, HostLayoutCouplingError
from ams.utils.provider_config import normalize_project_local_path

def test_resolution_provenance_reports_env(monkeypatch):
    monkeypatch.setenv("AMS_TEST_PROVENANCE_DIR", "/some/env/path")
    res = resolve_mutable_data_path(
        default_relative_path="default/path",
        env_var="AMS_TEST_PROVENANCE_DIR"
    )
    assert res.source == "ENV"
    assert str(res.path) == "/some/env/path"

def test_provider_config_uses_central_resolver():
    # normalize_project_local_path should correctly normalize using path_resolver
    path = normalize_project_local_path("data/test.csv")
    assert path.endswith("data/test.csv")

def test_provider_config_triggers_anti_regression():
    with pytest.raises(HostLayoutCouplingError):
        normalize_project_local_path("/root/projects/AMS/data/test.csv")

def test_provider_config_fail_fast_on_invalid_input():
    # normalize_project_local_path itself raises ValueError on empty strings
    with pytest.raises(ValueError):
        normalize_project_local_path("   ")

