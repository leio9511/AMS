import argparse
import os
import json
import sys
import datetime
import pandas as pd
import jqdatasdk
import logging

from etl.cb_provider_base import DataProviderError
from etl.jqdata_provider import JQDataProvider
from etl.tushare_provider import TuShareProvider
from etl.cb_etl_pipeline import (
    CBETLPipeline,
    STAGE_STATUS_PASS,
    STAGE_STATUS_FAIL,
    STAGE_STATUS_NOT_RUN,
    SUPPORTABILITY_BUCKET_SUPPORTABLE,
    SUPPORTABILITY_BUCKET_UNEXPECTED_CONTRACT_REGRESSION,
    CANONICAL_CB_COLUMNS,
    SUPPORTABILITY_EXCLUSION_BUCKETS,
    _extract_sorted_unique_codes,
    _build_underlying_mapping,
    _build_delist_mapping,
    _build_empty_canonical_cb_frame,
)
from ams.utils.provider_config import (
    get_provider_artifact_paths,
    load_provider_config,
    resolve_provider_name,
)

logger = logging.getLogger(__name__)

SUPPORTABILITY_REGRESSION_ERROR = "Missing underlying_ticker for supportable bonds in CONBOND_BASIC_INFO"

def get_provider(source_name, jqdata_client=None):
    if source_name == "jqdata":
        client = jqdata_client or jqdatasdk
        user = os.environ.get("JQDATA_USER")
        pwd = os.environ.get("JQDATA_PWD")
        if not user or not pwd:
            raise ValueError("Missing JQDATA_USER or JQDATA_PWD environment variables")
        try:
            client.auth(user, pwd)
        except Exception as e:
            logger.warning(f"JQData auth might have failed or is already active: {e}")
        return JQDataProvider(jqdata_client=client)
    elif source_name == "tushare":
        token = os.environ.get("TUSHARE_TOKEN")
        return TuShareProvider(token=token)
    else:
        raise ValueError(f"Unknown data source: {source_name}")

def _write_metrics(metrics_path: str, metrics: dict) -> None:
    os.makedirs(os.path.dirname(metrics_path), exist_ok=True)
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
        "underlying_ticker_nonnull_ratio": float(df["underlying_ticker"].notna().mean()) if "underlying_ticker" in df.columns else 0.0,
        "premium_rate_nonzero_ratio": float((df["premium_rate"] != 0).mean()) if "premium_rate" in df.columns else 0.0,
        "premium_rate_zero_ratio": float((df["premium_rate"] == 0).mean()) if "premium_rate" in df.columns else 0.0,
        "is_st_true_count": int(df["is_st"].sum()) if "is_st" in df.columns else 0,
        "is_redeemed_true_count": int(df["is_redeemed"].sum()) if "is_redeemed" in df.columns else 0,
    }

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

    metrics = {}
    for bucket_name, metric_keys in SUPPORTABILITY_EXCLUSION_BUCKETS.items():
        bucket_mask = df["supportability_bucket"].eq(bucket_name)
        filtered_codes = _extract_sorted_unique_codes(df.loc[bucket_mask, "bond_code_raw"])
        metrics[metric_keys["count_key"]] = len(filtered_codes)
        metrics[metric_keys["row_count_key"]] = int(bucket_mask.sum())
        metrics[metric_keys["codes_key"]] = filtered_codes
    return metrics

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
        sys.exit(1)

# Migration-period datasets from different providers must be stored as separate artifacts and must not silently overwrite one another.
def run_etl(start_date, end_date, source_name, promote=False, jqdata_client=None, dataset_path=None, metrics_path=None, 
            _underlying_mapping_func=None, _delist_mapping_func=None):
    config = load_provider_config()
    selected_provider = resolve_provider_name(source_name, config=config)
    provider_config = get_provider_artifact_paths(selected_provider, config=config)
    
    if dataset_path is None:
        dataset_path = provider_config["dataset_path"]
    if metrics_path is None:
        metrics_path = provider_config["metrics_path"]
    
    # Use provided helpers or default to pipeline ones
    u_map_func = _underlying_mapping_func or _build_underlying_mapping
    d_map_func = _delist_mapping_func or _build_delist_mapping

    provider = get_provider(selected_provider, jqdata_client=jqdata_client)
    pipeline = CBETLPipeline(start_date, end_date, provider=provider)
    
    print(f"Running ETL for {selected_provider} from {start_date} to {end_date}...")
    
    if not pipeline.run_stage_a_source_acquisition():
        if promote:
            raise ValueError(pipeline.results["source_coverage"]["message"])

    # Ensure pipeline uses potential patched helpers
    if pipeline.df_bonds_info is not None:
        pipeline.bond_to_stock = u_map_func(pipeline.df_bonds_info)
        pipeline.bond_to_delist = d_map_func(pipeline.df_bonds_info)

    if not pipeline.run_stage_b_supportability_classification():
         if promote:
             raise ValueError(SUPPORTABILITY_REGRESSION_ERROR)

    pipeline.run_stage_c_premium_join()
    pipeline.run_stage_d_is_st_join()
    pipeline.run_stage_e_redemption_delist()
    pipeline.run_stage_f_validator()
    
    report = pipeline.get_final_report()
    
    if not promote:
        # Audit mode
        report_filename = f"cb_etl_audit_{start_date}_{end_date}.json"
        report_dir = "/root/projects/AMS/reports"
        os.makedirs(report_dir, exist_ok=True)
        report_path = os.path.join(report_dir, report_filename)
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[AuditRunnerError] Failed to write audit report: {e}")
            raise RuntimeError(f"Audit report persistence failed: {e}")
        print(f"[AuditRunner] Audit report written to {report_path}")
        return report_path
    else:
        # Promote mode
        df = pipeline.df
        df_supportable = df[df["supportability_bucket"].eq(SUPPORTABILITY_BUCKET_SUPPORTABLE)].copy()

        promotion_status = report.get("validator_summary", {}).get("promotion_gate_status", "PASS")
        promotion_message = report.get("validator_summary", {}).get("promotion_gate_message", "")
        if promotion_status != "PASS":
            if promotion_message:
                print(promotion_message)
            core_validator_message = report.get("validator_summary", {}).get("core_validator_message", "")
            enrichment_validator_message = report.get("validator_summary", {}).get("enrichment_validator_message", "")
            if core_validator_message:
                print(core_validator_message)
            if enrichment_validator_message:
                print(enrichment_validator_message)
            print("[DataPromotionBlocked] Candidate research dataset failed promotion gate. Canonical dataset remains unchanged.")
            sys.exit(1)

        supportability_metrics = _build_supportability_exclusion_metrics(df)

        if df_supportable.empty:
            df_supportable_final = _build_empty_canonical_cb_frame()
            exclusion_only_window = True
        else:
            df_supportable_final = df_supportable[CANONICAL_CB_COLUMNS]
            exclusion_only_window = False

        premium_rate_metrics = {
            "provenance": selected_provider,
            "start_date": start_date,
            "end_date": end_date,
            "generated_at": datetime.datetime.now().isoformat(),
            "source_lineage": "jqdata_sync_cb" if selected_provider == "jqdata" else f"cb_etl_runner_{selected_provider}",
            "premium_rate_source_row_count": pipeline.results["source_coverage"].get("premium_source_row_count", 0),
            "premium_rate_joined_row_count": pipeline.results["premium_join_summary"].get("premium_joined_row_count", 0),
            "premium_rate_join_coverage_ratio": 1.0 - pipeline.results["premium_join_summary"].get("missing_premium_ratio", 0.0) if not df_supportable.empty else 0.0,
            "is_redeemed_missing_delist_count": pipeline.results["redemption_summary"].get("missing_redemption_row_count", 0),
            **_build_candidate_summary_metrics(df_supportable_final),
            **supportability_metrics,
            "full_report": report
        }
        
        tmp_metrics_path = metrics_path + ".tmp"
        _write_metrics(tmp_metrics_path, premium_rate_metrics)

        if exclusion_only_window:
            _promote_exclusion_only_metrics(tmp_metrics_path, metrics_path)
            print("[ExclusionOnlyWindow] No supportable bonds survived; metrics updated and canonical dataset remains unchanged.")
            return

        # Atomic promotion logic
        tmp_path = dataset_path + ".tmp"
        df_supportable_final.to_csv(tmp_path, index=False)

        bak_path = dataset_path + ".bak"
        metrics_bak_path = metrics_path + ".bak"
        dataset_existed = os.path.exists(dataset_path)
        metrics_existed = os.path.exists(metrics_path)
        
        try:
            if dataset_existed:
                os.replace(dataset_path, bak_path)
            if metrics_existed:
                os.replace(metrics_path, metrics_bak_path)
                
            os.replace(tmp_path, dataset_path)
            os.replace(tmp_metrics_path, metrics_path)
            print(f"[PromoteRunner] Successfully promoted {selected_provider} dataset to {dataset_path}")
        except Exception as e:
            if dataset_existed and os.path.exists(bak_path):
                os.replace(bak_path, dataset_path)
            if metrics_existed and os.path.exists(metrics_bak_path):
                os.replace(metrics_bak_path, metrics_path)
            print(f"[PromoteRunner] Promotion failed: {e}")
            sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AMS CB ETL Runner")
    parser.add_argument("--data-source", type=str, default="auto", choices=["auto", "jqdata", "tushare"], help="Data source provider for automatic path selection. CLI explicit parameter overrides AMS local provider default configuration.")
    parser.add_argument("--start", type=str, default="2025-01-06", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default="2025-02-06", help="End date (YYYY-MM-DD)")
    parser.add_argument("--audit", action="store_true", help="Run in audit mode (no promotion)")
    parser.add_argument("--promote", action="store_true", help="Run in promotion mode")
    
    args = parser.parse_args()
    
    config = load_provider_config()
    source = resolve_provider_name(args.data_source, config=config)
    if args.data_source == "auto":
        print(f"Using default provider: {source}")
        
    is_promote = args.promote or not args.audit
    
    run_etl(args.start, args.end, source, promote=is_promote)
