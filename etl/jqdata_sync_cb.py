import json
import os
import datetime
import sys
import pandas as pd
import jqdatasdk

from etl.cb_provider_base import DataProviderError
from etl.jqdata_provider import JQDataProvider
from etl.cb_etl_pipeline import (
    CBETLPipeline,
    STAGE_STATUS_PASS,
    STAGE_STATUS_FAIL,
    STAGE_STATUS_NOT_RUN,
    SUPPORTABILITY_BUCKET_SUPPORTABLE,
    SUPPORTABILITY_BUCKET_UNEXPECTED_CONTRACT_REGRESSION,
    CANONICAL_CB_COLUMNS,
    _split_bond_ticker,
    _prepare_basic_info_contract,
    _build_underlying_mapping,
    _build_delist_mapping,
    _build_bond_key_columns,
    _normalize_premium_source,
    REDEMPTION_SOURCE_CONTRACT,
)

METRICS_PATH = "/root/projects/AMS/data/cb_history_factors.metrics.json"
DATA_PATH = "/root/projects/AMS/data/cb_history_factors.csv"
LEGACY_UNDERLYING_SOURCE_FATAL = (
    "[FATAL] Invalid underlying-ticker source contract: get_security_info(ticker).parent "
    "is not valid for AMS convertible bonds."
)
LEGACY_REDEMPTION_SOURCE_FATAL = (
    "[FATAL] Invalid redemption source contract: finance.CCB_CALL is not a valid "
    "JQData table for AMS convertible-bond lifecycle semantics."
)
SUPPORTABILITY_REGRESSION_ERROR = "Missing underlying_ticker for supportable bonds in CONBOND_BASIC_INFO"

def _raise_legacy_underlying_source_error() -> None:
    raise RuntimeError(LEGACY_UNDERLYING_SOURCE_FATAL)

def _raise_legacy_redemption_source_error() -> None:
    raise RuntimeError(LEGACY_REDEMPTION_SOURCE_FATAL)

def _write_metrics(metrics_path: str, metrics: dict) -> None:
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

def _build_candidate_summary_metrics(df: pd.DataFrame) -> dict:
    row_count = int(len(df))
    if row_count == 0:
        return {
            "row_count": 0,
            "underlying_ticker_nonnull_ratio": 0.0,
            "premium_rate_nonzero_ratio": 0.0,
            "premium_rate_zero_ratio": 0.0,
            "is_st_true_count": 0,
            "is_redeemed_true_count": 0,
        }

    return {
        "row_count": row_count,
        "underlying_ticker_nonnull_ratio": float(df["underlying_ticker"].notna().mean()),
        "premium_rate_nonzero_ratio": float((df["premium_rate"] != 0).mean()),
        "premium_rate_zero_ratio": float((df["premium_rate"] == 0).mean()),
        "is_st_true_count": int(df["is_st"].sum()),
        "is_redeemed_true_count": int(df["is_redeemed"].sum()),
    }

def _promote_exclusion_only_metrics(tmp_metrics_path: str, metrics_path: str) -> None:
    metrics_bak_path = metrics_path + ".bak"
    metrics_backed_up = False
    metrics_existed = os.path.exists(metrics_path)

    try:
        if metrics_existed:
            os.replace(metrics_path, metrics_bak_path)
            metrics_backed_up = True

        os.replace(tmp_metrics_path, metrics_path)
    except Exception:
        if metrics_backed_up:
            os.replace(metrics_bak_path, metrics_path)
        elif not metrics_existed and os.path.exists(metrics_path):
            os.remove(metrics_path)

        if os.path.exists(tmp_metrics_path):
            os.remove(tmp_metrics_path)

        print("[DataPromotionRollback] Exclusion-only metrics promotion failed. Canonical dataset remains unchanged.")
        import sys

        sys.exit(1)

def _build_supportability_exclusion_metrics(df: pd.DataFrame) -> dict:
    if df is None or df.empty or "supportability_bucket" not in df.columns:
        return {
            "filtered_bonds_outside_basic_info_count": 0,
            "filtered_rows_outside_basic_info_count": 0,
            "filtered_bond_codes_outside_basic_info": [],
            "filtered_bonds_missing_company_code_legacy_count": 0,
            "filtered_rows_missing_company_code_legacy_count": 0,
            "filtered_bond_codes_missing_company_code_legacy": [],
        }

    from etl.cb_etl_pipeline import SUPPORTABILITY_EXCLUSION_BUCKETS, _extract_sorted_unique_codes
    metrics = {}
    for bucket_name, metric_keys in SUPPORTABILITY_EXCLUSION_BUCKETS.items():
        bucket_mask = df["supportability_bucket"].eq(bucket_name)
        filtered_codes = _extract_sorted_unique_codes(df.loc[bucket_mask, "bond_code_raw"])
        metrics[metric_keys["count_key"]] = len(filtered_codes)
        metrics[metric_keys["row_count_key"]] = int(bucket_mask.sum())
        metrics[metric_keys["codes_key"]] = filtered_codes
    return metrics

def sync_cb_data(start_date="2025-01-06", end_date="2025-02-06"):
    """
    Production Promote Runner: fail-fast + promotion.
    """
    output_path = DATA_PATH
    bak_path = output_path + ".bak"
    metrics_path = METRICS_PATH

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    user = os.environ.get("JQDATA_USER")
    pwd = os.environ.get("JQDATA_PWD")

    if not user or not pwd:
        raise ValueError("Missing JQDATA_USER or JQDATA_PWD environment variables")

    try:
        jqdatasdk.auth(user, pwd)
    except Exception as e:
        raise RuntimeError(f"JQData auth failed: {e}")

    provider = JQDataProvider(jqdata_client=jqdatasdk)
    pipeline = CBETLPipeline(start_date, end_date, provider=provider)

    # Stage A: Source acquisition
    if not pipeline.run_stage_a_source_acquisition():
        # Match old error type/message
        raise ValueError(pipeline.results["source_coverage"]["message"])

    # Ensure pipeline uses potentially patched helper functions from this module
    pipeline.bond_to_stock = _build_underlying_mapping(pipeline.df_bonds_info)
    pipeline.bond_to_delist = _build_delist_mapping(pipeline.df_bonds_info)

    # Stage B: Supportability classification
    if not pipeline.run_stage_b_supportability_classification():
         raise ValueError(SUPPORTABILITY_REGRESSION_ERROR)

    # Stage C: Premium join
    if not pipeline.run_stage_c_premium_join():
         # In production, we might still want to proceed if it's not a fatal error 
         # but the old code would fail if ANY record is missing premium rate.
         pass

    # Stage D: is_st join
    if not pipeline.run_stage_d_is_st_join():
         pass

    # Stage E: Redemption/delist
    if not pipeline.run_stage_e_redemption_delist():
         pass

    # Strict production checks (ANY NA fails)
    df = pipeline.df
    df_supportable = df[df["supportability_bucket"].eq(SUPPORTABILITY_BUCKET_SUPPORTABLE)].copy()
    
    if not df_supportable.empty:
        # Check for underlying_ticker missing (regression)
        # Note: run_stage_b already checks for supportable bonds in basic info, 
        # but if the mapping itself failed for some reason...
        if "underlying_ticker" not in df_supportable.columns or df_supportable["underlying_ticker"].isna().any():
             raise ValueError(SUPPORTABILITY_REGRESSION_ERROR)

        if "premium_rate" not in df_supportable.columns or df_supportable["premium_rate"].isna().any():
            raise ValueError("Missing premium_rate for some records")
        if "is_st" not in df_supportable.columns or df_supportable["is_st"].isna().any():
            raise ValueError("Missing is_st for some records")
        if "is_redeemed" not in df_supportable.columns or df_supportable["is_redeemed"].isna().any():
            raise ValueError("Missing is_redeemed for some records")

    # Post-stages processing for promotion
    supportability_metrics = _build_supportability_exclusion_metrics(df)

    if df_supportable.empty:
        from etl.cb_etl_pipeline import _build_empty_canonical_cb_frame
        df_supportable_final = _build_empty_canonical_cb_frame()
        exclusion_only_window = True
    else:
        df_supportable_final = df_supportable[CANONICAL_CB_COLUMNS]
        exclusion_only_window = False

    premium_rate_metrics = {
        "premium_rate_source_row_count": pipeline.results["source_coverage"].get("premium_source_row_count", 0),
        "premium_rate_joined_row_count": pipeline.results["premium_join_summary"].get("premium_joined_row_count", 0),
        "premium_rate_join_coverage_ratio": 1.0 - pipeline.results["premium_join_summary"].get("missing_premium_ratio", 0.0) if not df_supportable.empty else 0.0,
        "is_redeemed_missing_delist_count": pipeline.results["redemption_summary"].get("missing_redemption_row_count", 0),
    }
    
    premium_rate_metrics.update({
        **_build_candidate_summary_metrics(df_supportable_final),
        **supportability_metrics,
        "generated_at": datetime.datetime.now().isoformat(),
        "source_lineage": "jqdata_sync_cb"
    })

    tmp_metrics_path = metrics_path + ".tmp"
    _write_metrics(tmp_metrics_path, premium_rate_metrics)

    if exclusion_only_window:
        _promote_exclusion_only_metrics(tmp_metrics_path, metrics_path)
        print(
            "[ExclusionOnlyWindow] No supportable bonds survived; metrics updated and canonical dataset remains unchanged."
        )
        return

    # Stage F: Validator
    if not pipeline.run_stage_f_validator():
         val_summary = pipeline.results["validator_summary"]
         if val_summary.get("schema_validator_message"):
             print(val_summary["schema_validator_message"])
         if val_summary.get("semantic_validator_message"):
             print(val_summary["semantic_validator_message"])
         print("[DataPromotionBlocked] Candidate research dataset failed validation. Canonical dataset remains unchanged.")
         sys.exit(1)

    # Promotion
    tmp_path = output_path + ".tmp"
    df_supportable_final.to_csv(tmp_path, index=False)

    canonical_backed_up = False
    metrics_backed_up = False
    metrics_bak_path = metrics_path + ".bak"
    canonical_existed = os.path.exists(output_path)
    metrics_existed = os.path.exists(metrics_path)
    
    try:
        if canonical_existed:
            os.replace(output_path, bak_path)
            canonical_backed_up = True
        if metrics_existed:
            os.replace(metrics_path, metrics_bak_path)
            metrics_backed_up = True
        
        os.replace(tmp_path, output_path)
        os.replace(tmp_metrics_path, metrics_path)
        print(f"Successfully synced data to {output_path}")
    except Exception as e:
        if canonical_backed_up:
            os.replace(bak_path, output_path)
        elif not canonical_existed and os.path.exists(output_path):
            os.remove(output_path)
            
        if metrics_backed_up:
            os.replace(metrics_bak_path, metrics_path)
        elif not metrics_existed and os.path.exists(metrics_path):
            os.remove(metrics_path)
            
        print(f"[DataPromotionRollback] Atomic promotion failed: {e}. Canonical dataset restored from backup.")
        sys.exit(1)

def audit_cb_data(start_date, end_date):
    """
    Audit Runner: collect + report, no promotion.
    """
    user = os.environ.get("JQDATA_USER")
    pwd = os.environ.get("JQDATA_PWD")

    if not user or not pwd:
        raise ValueError("Missing JQDATA_USER or JQDATA_PWD environment variables")

    try:
        jqdatasdk.auth(user, pwd)
    except Exception:
        # Auth might already be active or fail in a way that allows read-only probe
        pass

    provider = JQDataProvider(jqdata_client=jqdatasdk)
    pipeline = CBETLPipeline(start_date, end_date, provider=provider)
    
    pipeline.run_stage_a_source_acquisition()
    
    # Audit runner should also use potentially patched helpers if called in a test context
    pipeline.bond_to_stock = _build_underlying_mapping(pipeline.df_bonds_info)
    pipeline.bond_to_delist = _build_delist_mapping(pipeline.df_bonds_info)

    pipeline.run_stage_b_supportability_classification()
    pipeline.run_stage_c_premium_join()
    pipeline.run_stage_d_is_st_join()
    pipeline.run_stage_e_redemption_delist()
    pipeline.run_stage_f_validator()
    
    report = pipeline.get_final_report()
    
    report_filename = f"cb_etl_audit_{start_date}_{end_date}.json"
    report_dir = "/root/projects/AMS/reports"
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, report_filename)
    
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except Exception as e:
        # CRITICAL: Audit-mode report write failure must not trigger promotion rollback logic.
        # Since we are in audit_cb_data, we just fail explicitly.
        print(f"[AuditRunnerError] Failed to write audit report: {e}")
        raise RuntimeError(f"Audit report persistence failed: {e}")
    
    print(f"[AuditRunner] Audit report written to {report_path}")
    return report_path

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--audit":
        start = sys.argv[2] if len(sys.argv) > 2 else "2025-01-06"
        end = sys.argv[3] if len(sys.argv) > 3 else "2025-02-06"
        audit_cb_data(start, end)
    else:
        sync_cb_data()
