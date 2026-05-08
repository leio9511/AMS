import os
import sys

import jqdatasdk
from ams.utils.path_resolver import resolve_mutable_data_path, resolve_runtime_output_path, validate_no_host_coupling
from etl.cb_etl_runner import (
    run_etl,
    SUPPORTABILITY_REGRESSION_ERROR,
    _write_metrics,
    _build_candidate_summary_metrics,
    _promote_exclusion_only_metrics,
    _build_supportability_exclusion_metrics,
)
from etl.cb_etl_pipeline import (
    _split_bond_ticker,
    _prepare_basic_info_contract,
    _build_underlying_mapping,
    _build_delist_mapping,
    _build_bond_key_columns,
    _normalize_premium_source,
    REDEMPTION_SOURCE_CONTRACT,
)

# Public compatibility hooks.  The default values are contract-safe sentinels;
# callers/tests may patch them to explicit non-host-coupled paths.
_DEFAULT_DATA_PATH = "data/cb_history_factors_jqdata.csv"
_DEFAULT_METRICS_PATH = "data/cb_history_factors_jqdata.metrics.json"
DATA_PATH = _DEFAULT_DATA_PATH
METRICS_PATH = _DEFAULT_METRICS_PATH
LEGACY_UNDERLYING_SOURCE_FATAL = (
    "[FATAL] Invalid underlying-ticker source contract: get_security_info(ticker).parent "
    "is not valid for AMS convertible bonds."
)
LEGACY_REDEMPTION_SOURCE_FATAL = (
    "[FATAL] Invalid redemption source contract: finance.CCB_CALL is not a valid "
    "JQData table for AMS convertible-bond lifecycle semantics."
)

def _raise_legacy_underlying_source_error() -> None:
    raise RuntimeError(LEGACY_UNDERLYING_SOURCE_FATAL)

def _raise_legacy_redemption_source_error() -> None:
    raise RuntimeError(LEGACY_REDEMPTION_SOURCE_FATAL)

def _compatibility_path_override(current_value, *, default_value: str, path_kind: str) -> str | None:
    """Return a contract-validated explicit override when legacy hooks are patched."""
    if current_value is None:
        return None

    current_str = str(current_value).strip()
    if not current_str or current_str == default_value:
        return None

    validate_no_host_coupling(current_str)
    resolver = resolve_mutable_data_path if path_kind == "dataset" else resolve_runtime_output_path
    return str(
        resolver(
            default_relative_path=default_value,
            cli_override=current_str,
        ).path
    )


def _sync_dataset_override() -> str | None:
    return _compatibility_path_override(
        DATA_PATH,
        default_value=_DEFAULT_DATA_PATH,
        path_kind="dataset",
    )


def _sync_metrics_override() -> str | None:
    return _compatibility_path_override(
        METRICS_PATH,
        default_value=_DEFAULT_METRICS_PATH,
        path_kind="metrics",
    )


def sync_cb_data(start_date="2025-01-06", end_date="2025-02-06"):
    """Legacy shim for sync_cb_data."""
    return run_etl(start_date, end_date, "jqdata", promote=True, jqdata_client=jqdatasdk, 
                   dataset_path=_sync_dataset_override(), metrics_path=_sync_metrics_override(),
                   _underlying_mapping_func=_build_underlying_mapping,
                   _delist_mapping_func=_build_delist_mapping)

def audit_cb_data(start_date="2025-01-06", end_date="2025-02-06"):
    """Legacy shim for audit_cb_data."""
    return run_etl(start_date, end_date, "jqdata", promote=False, jqdata_client=jqdatasdk,
                   dataset_path=_sync_dataset_override(), metrics_path=_sync_metrics_override(),
                   _underlying_mapping_func=_build_underlying_mapping,
                   _delist_mapping_func=_build_delist_mapping)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--audit":
        start = sys.argv[2] if len(sys.argv) > 2 else "2025-01-06"
        end = sys.argv[3] if len(sys.argv) > 3 else "2025-02-06"
        audit_cb_data(start, end)
    else:
        sync_cb_data()
