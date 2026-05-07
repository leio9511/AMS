import os
import sys
import jqdatasdk
from ams.utils.provider_config import get_provider_artifact_paths
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

# Legacy constants for compatibility with tests
_JQDATA_PATHS = get_provider_artifact_paths("jqdata")
DATA_PATH = _JQDATA_PATHS["dataset_path"]
METRICS_PATH = _JQDATA_PATHS["metrics_path"]
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

def sync_cb_data(start_date="2025-01-06", end_date="2025-02-06"):
    """Legacy shim for sync_cb_data."""
    return run_etl(start_date, end_date, "jqdata", promote=True, jqdata_client=jqdatasdk, 
                   dataset_path=DATA_PATH, metrics_path=METRICS_PATH,
                   _underlying_mapping_func=_build_underlying_mapping,
                   _delist_mapping_func=_build_delist_mapping)

def audit_cb_data(start_date="2025-01-06", end_date="2025-02-06"):
    """Legacy shim for audit_cb_data."""
    return run_etl(start_date, end_date, "jqdata", promote=False, jqdata_client=jqdatasdk,
                   dataset_path=DATA_PATH, metrics_path=METRICS_PATH,
                   _underlying_mapping_func=_build_underlying_mapping,
                   _delist_mapping_func=_build_delist_mapping)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--audit":
        start = sys.argv[2] if len(sys.argv) > 2 else "2025-01-06"
        end = sys.argv[3] if len(sys.argv) > 3 else "2025-02-06"
        audit_cb_data(start, end)
    else:
        sync_cb_data()
