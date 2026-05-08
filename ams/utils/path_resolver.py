import os
from pathlib import Path
from dataclasses import dataclass

@dataclass
class ResolutionResult:
    path: Path
    source: str
    
    def __fspath__(self):
        return str(self.path)

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
    
    validate_no_host_coupling(path_obj)
    
    repo_root = get_repo_root()
    resolved = (repo_root / path_obj).resolve()
        
    if not resolved.is_relative_to(repo_root):
        raise ValueError(f"Path {path_obj} resolves outside the repository root {repo_root}")
        
    return resolved

def _resolve_path_with_precedence(
    default_relative_path: str | Path,
    cli_override: str | Path | None = None,
    env_var: str | None = None,
    config_override: str | Path | None = None,
) -> ResolutionResult:
    candidates = []
    if cli_override is not None:
        candidates.append(("CLI", cli_override))
    
    if env_var is not None:
        env_val = os.environ.get(env_var)
        if env_val is not None:
            candidates.append(("ENV", env_val))
    
    if config_override is not None:
        candidates.append(("CONFIG", config_override))
    
    for source, val in candidates:
        val_str = str(val).strip()
        if not val_str:
            raise ValueError(f"Invalid path provided via {source}: empty string")
        validate_no_host_coupling(val_str)
        path_obj = Path(val_str).expanduser()
        if path_obj.is_absolute():
            resolved_path = path_obj.resolve()
        else:
            resolved_path = (get_repo_root() / path_obj).resolve()
        validate_no_host_coupling(resolved_path)
        return ResolutionResult(path=resolved_path, source=source)
        
    # Default fallback
    val_str = str(default_relative_path).strip()
    if not val_str:
        raise ValueError("Invalid default path: empty string")
    validate_no_host_coupling(val_str)
    
    return ResolutionResult(path=(get_repo_root() / Path(val_str)).resolve(), source="DEFAULT")

def resolve_mutable_data_path(
    default_relative_path: str | Path,
    cli_override: str | Path | None = None,
    env_var: str | None = None,
    config_override: str | Path | None = None,
) -> ResolutionResult:
    """
    Resolves mutable research/backtest data path following precedence:
    CLI > ENV > AMS-owned config > project-local default
    """
    return _resolve_path_with_precedence(
        default_relative_path, cli_override, env_var, config_override
    )

def resolve_runtime_output_path(
    default_relative_path: str | Path,
    cli_override: str | Path | None = None,
    env_var: str | None = None,
    config_override: str | Path | None = None,
) -> ResolutionResult:
    """
    Resolves runtime outputs/state path following precedence:
    CLI > ENV > AMS-owned config > project-local default
    """
    return _resolve_path_with_precedence(
        default_relative_path, cli_override, env_var, config_override
    )
