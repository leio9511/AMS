import os
from pathlib import Path

class HostLayoutCouplingError(ValueError):
    """Raised when a path incorrectly couples with host-specific environments."""
    pass

def validate_no_host_coupling(path: Path | str) -> None:
    """
    Validates that the given path does not contain host-specific hardcoded layouts.
    """
    path_str = str(path).replace('\\', '/')
    prohibited = [
        "/root/projects/AMS",
        "/root/.openclaw",
        ".openclaw/workspace"
    ]
    for p in prohibited:
        if p in path_str:
            raise HostLayoutCouplingError(f"Path contains prohibited host layout coupling: {p}")

def get_repo_root() -> Path:
    """
    Returns the absolute path of the AMS project root.
    Calculated relative to this file's location to ensure it is independent of cwd.
    """
    return Path(__file__).resolve().parent.parent.parent

def resolve_repo_asset(relative_path: str | Path) -> Path:
    """
    Resolves a repo-owned stable asset relative to the repository root.
    Rejects absolute paths that point outside the repository.
    Validates against host-layout coupling regressions.
    """
    path_obj = Path(relative_path)
    
    if path_obj.is_absolute():
        repo_root = get_repo_root()
        try:
            path_obj.relative_to(repo_root)
        except ValueError:
            raise ValueError(f"Absolute path {path_obj} is outside the repository root {repo_root}")
        resolved = path_obj.resolve()
    else:
        resolved = (get_repo_root() / path_obj).resolve()
        
    validate_no_host_coupling(resolved)
    return resolved
