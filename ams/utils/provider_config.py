import json
import os
import re
from pathlib import Path
from typing import Any, Callable, Mapping

from ams.utils.path_resolver import (
    ResolutionResult,
    get_repo_root as _get_repo_root,
    resolve_mutable_data_path,
    resolve_runtime_output_path,
    validate_no_host_coupling,
)

DEFAULT_CONFIG_PATH = _get_repo_root() / "ams_config.json"
DEFAULT_PROVIDER = "jqdata"
_PROVIDER_PATH_KEYS = ("dataset_path", "metrics_path")
_DEFAULT_PROVIDER_ARTIFACTS = {
    "jqdata": {
        "dataset_path": "data/cb_history_factors_jqdata.csv",
        "metrics_path": "data/cb_history_factors_jqdata.metrics.json",
    },
    "tushare": {
        "dataset_path": "data/cb_history_factors_tushare.csv",
        "metrics_path": "data/cb_history_factors_tushare.metrics.json",
    },
}
_PROVIDER_PATH_RESOLVERS: dict[str, Callable[..., ResolutionResult]] = {
    "dataset_path": resolve_mutable_data_path,
    "metrics_path": resolve_runtime_output_path,
}


def get_repo_root() -> Path:
    return _get_repo_root()


def resolve_project_path(*parts: str) -> str:
    return str(_get_repo_root().joinpath(*parts))


def normalize_project_local_path(path_value: str) -> str:
    res = resolve_mutable_data_path(default_relative_path=path_value)
    return str(res.path)


def _default_provider_config() -> dict[str, Any]:
    return {
        "default_provider": DEFAULT_PROVIDER,
        "providers": {
            provider_name: dict(provider_artifacts)
            for provider_name, provider_artifacts in _DEFAULT_PROVIDER_ARTIFACTS.items()
        },
    }


def _load_raw_config(config_path: Path) -> dict[str, Any]:
    try:
        with config_path.open("r", encoding="utf-8") as f:
            raw_config = json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed provider config JSON in {config_path}: {exc.msg}") from exc
    except OSError as exc:
        raise ValueError(f"Unable to read provider config at {config_path}: {exc}") from exc

    if not isinstance(raw_config, dict):
        raise ValueError(f"Provider config at {config_path} must be a JSON object")

    return raw_config


def _validate_provider_entry(provider_name: str, provider_config: Any, *, config_path: Path) -> None:
    if not isinstance(provider_config, dict):
        raise ValueError(
            f"Provider '{provider_name}' in {config_path} must be a JSON object"
        )

    for key in _PROVIDER_PATH_KEYS:
        value = provider_config.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"Provider '{provider_name}' in {config_path} is missing required key '{key}'"
            )


def _validate_raw_override_config(raw_config: Mapping[str, Any], *, config_path: Path) -> None:
    providers = raw_config.get("providers")
    if not isinstance(providers, dict) or not providers:
        raise ValueError(f"Provider config at {config_path} must define a non-empty 'providers' object")

    if "default_provider" in raw_config:
        default_provider = raw_config["default_provider"]
        if not isinstance(default_provider, str) or not default_provider.strip():
            raise ValueError(f"default_provider in {config_path} must be a non-empty string")

    for provider_name, provider_config in providers.items():
        if not isinstance(provider_name, str) or not provider_name.strip():
            raise ValueError(f"Provider names in {config_path} must be non-empty strings")
        _validate_provider_entry(provider_name, provider_config, config_path=config_path)


def _merge_provider_configs(base_config: dict[str, Any], override_config: Mapping[str, Any]) -> dict[str, Any]:
    merged = {
        "default_provider": base_config["default_provider"],
        "providers": {
            provider_name: dict(provider_config)
            for provider_name, provider_config in base_config["providers"].items()
        },
    }

    if "default_provider" in override_config:
        merged["default_provider"] = override_config["default_provider"]

    for provider_name, provider_config in override_config["providers"].items():
        merged["providers"][provider_name] = dict(provider_config)

    return merged


def _normalize_env_fragment(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", value.strip()).strip("_").upper()


def _provider_artifact_env_var(provider_name: str, key: str) -> str:
    return f"AMS_{_normalize_env_fragment(provider_name)}_{key.upper()}"


def _default_artifact_path(provider_name: str, key: str, configured_value: str) -> str:
    return _DEFAULT_PROVIDER_ARTIFACTS.get(provider_name, {}).get(key, configured_value)


def _resolve_provider_artifact(
    provider_name: str,
    key: str,
    configured_value: str,
    *,
    override_provider_names: set[str],
) -> str:
    validate_no_host_coupling(configured_value)
    resolver = _PROVIDER_PATH_RESOLVERS[key]
    config_override = configured_value if provider_name in override_provider_names else None
    result = resolver(
        default_relative_path=_default_artifact_path(provider_name, key, configured_value),
        env_var=_provider_artifact_env_var(provider_name, key),
        config_override=config_override,
    )
    return str(result.path)


def _normalize_and_validate_config(
    config: Mapping[str, Any],
    *,
    override_provider_names: set[str] | None = None,
) -> dict[str, Any]:
    override_provider_names = override_provider_names or set()
    default_provider = config.get("default_provider", DEFAULT_PROVIDER)
    if not isinstance(default_provider, str) or not default_provider.strip():
        raise ValueError("default_provider must be a non-empty string")
    default_provider = default_provider.strip()

    providers = config.get("providers")
    if not isinstance(providers, dict) or not providers:
        raise ValueError("providers must be a non-empty object")

    normalized_providers: dict[str, dict[str, str]] = {}
    for provider_name, provider_config in providers.items():
        if not isinstance(provider_name, str) or not provider_name.strip():
            raise ValueError("Provider names must be non-empty strings")
        if not isinstance(provider_config, dict):
            raise ValueError(f"Provider '{provider_name}' must be a JSON object")

        normalized_provider_name = provider_name.strip()
        normalized_provider: dict[str, str] = {}
        for key in _PROVIDER_PATH_KEYS:
            value = provider_config.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Provider '{provider_name}' is missing required key '{key}'")
            normalized_provider[key] = _resolve_provider_artifact(
                normalized_provider_name,
                key,
                value,
                override_provider_names=override_provider_names,
            )

        normalized_providers[normalized_provider_name] = normalized_provider

    if default_provider not in normalized_providers:
        raise ValueError(f"Unknown default provider: {default_provider}")

    return {
        "default_provider": default_provider,
        "providers": normalized_providers,
    }


def load_provider_config() -> dict[str, Any]:
    config = _default_provider_config()
    config_path = Path(os.environ.get("AMS_CONFIG_PATH", DEFAULT_CONFIG_PATH))
    override_provider_names: set[str] = set()

    if config_path.exists():
        override_config = _load_raw_config(config_path)
        _validate_raw_override_config(override_config, config_path=config_path)
        config = _merge_provider_configs(config, override_config)
        override_provider_names = {
            provider_name.strip()
            for provider_name in override_config["providers"]
            if isinstance(provider_name, str)
        }

    return _normalize_and_validate_config(
        config,
        override_provider_names=override_provider_names,
    )


def resolve_provider_name(provider_name: str | None = None, *, config: Mapping[str, Any] | None = None) -> str:
    active_config = config or load_provider_config()
    requested_provider = provider_name or "auto"
    if requested_provider == "auto":
        requested_provider = active_config["default_provider"]

    if requested_provider not in active_config["providers"]:
        raise ValueError(f"Unknown provider: {requested_provider}")

    return requested_provider


def get_provider_artifact_paths(provider_name: str | None = None, *, config: Mapping[str, Any] | None = None) -> dict[str, str]:
    active_config = config or load_provider_config()
    selected_provider = resolve_provider_name(provider_name, config=active_config)
    return dict(active_config["providers"][selected_provider])
