import pytest
from pathlib import Path

from ams.utils.path_resolver import (
    get_repo_root,
    resolve_repo_asset,
    validate_no_host_coupling,
    HostLayoutCouplingError
)

def test_get_repo_root():
    root = get_repo_root()
    assert root.is_absolute()
    assert (root / "ams").is_dir()
    assert (root / "ams" / "utils").is_dir()

def test_resolve_repo_asset_valid():
    resolved = resolve_repo_asset("data/schema.json")
    assert resolved.is_absolute()
    assert resolved == get_repo_root() / "data" / "schema.json"

def test_resolve_repo_asset_rejects_external_absolute_path():
    with pytest.raises(ValueError, match="outside the repository root"):
        resolve_repo_asset("/tmp/some/external/path")

def test_resolve_repo_asset_rejects_escaping_relative_path():
    with pytest.raises(ValueError, match="resolves outside the repository root"):
        resolve_repo_asset("../../../external/path")

def test_anti_regression_guard_rejects_root_ams():
    with pytest.raises(HostLayoutCouplingError):
        validate_no_host_coupling("/root/projects/AMS/data/schema.json")

def test_anti_regression_guard_rejects_root_openclaw():
    with pytest.raises(HostLayoutCouplingError):
        validate_no_host_coupling("/root/.openclaw/some_file")

def test_anti_regression_guard_rejects_openclaw_workspace():
    with pytest.raises(HostLayoutCouplingError):
        validate_no_host_coupling("/tmp/.openclaw/workspace/data")

def test_resolve_repo_asset_accepts_internal_absolute_path():
    repo_root = get_repo_root()
    abs_path = repo_root / "data" / "schema.json"
    resolved = resolve_repo_asset(abs_path)
    assert resolved == abs_path

def test_resolve_repo_asset_rejects_escaping_absolute_path():
    repo_root = get_repo_root()
    abs_path = repo_root / ".." / "external" / "path"
    with pytest.raises(ValueError, match="resolves outside the repository root"):
        resolve_repo_asset(abs_path)
