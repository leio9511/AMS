from __future__ import annotations

from copy import deepcopy

EXECUTION_MODE_AUDIT = "audit"

STAGE_STATUS_PASS = "PASS"
STAGE_STATUS_FAIL = "FAIL"
STAGE_STATUS_NOT_RUN = "NOT_RUN"
STAGE_STATUS_DEGRADED = "DEGRADED"

PROMOTION_STATUS_PASS = "PASS"
PROMOTION_STATUS_BLOCKED = "BLOCKED"
PROMOTION_STATUS_NOT_RUN = "NOT_RUN"

FINAL_STATUS_PASS = "PASS"
FINAL_STATUS_FAIL_ROOT_BLOCKER = "FAIL_ROOT_BLOCKER"
FINAL_STATUS_FAIL_SECONDARY_ONLY = "FAIL_SECONDARY_ONLY"

FAILURE_TYPE_NONE = "NONE"

NON_PROMOTION_DISCLAIMER = "[AUDIT-ONLY] This run is diagnostic only. No canonical dataset promotion was attempted."

ROOT_BLOCKER_STAGES = {"A", "B", "C", "D", "E", "F", "ORCH"}
SECONDARY_FINDING_STAGES = {"B", "C", "D", "E"}

ROOT_BLOCKER_TYPES = {
    "SOURCE_AUTH_FAILURE",
    "PRICE_SOURCE_UNREADABLE",
    "SUPPORTABILITY_REGRESSION",
    "PREMIUM_SOURCE_TRUNCATION",
    "PREMIUM_RATE_MISSING_BROAD_COVERAGE",
    "RATE_LIMITED_ENRICHMENT",
    "PERMISSION_DEGRADED_ENRICHMENT",
    "IS_ST_SOURCE_GAP",
    "REDEMPTION_SOURCE_GAP",
    "VALIDATOR_SCHEMA_FAILURE",
    "VALIDATOR_SEMANTIC_FAILURE",
    "CONCURRENT_RUN_BLOCKED",
}

SECONDARY_FINDING_TYPES = {
    "MISSING_PREMIUM_RATE_ROWS",
    "MISSING_REDEMPTION_ROWS",
    "MISSING_IS_ST_ROWS",
    "MISSING_UNDERLYING_TICKER_ROWS",
    "EXCLUSION_ONLY_WINDOW",
}

ACTIVE_UNIVERSE_SUMMARY_TEMPLATE = {
    "core_price_row_count_before_filter": 0,
    "core_price_row_count_after_filter": 0,
    "all_null_ohlcv_row_count_filtered": 0,
    "core_universe_row_count": 0,
    "core_universe_unique_bond_count": 0,
    "active_bond_universe_count": 0,
    "enrichment_target_row_count": 0,
    "enrichment_target_unique_bond_count": 0,
}

SOURCE_COVERAGE_TEMPLATE = {
    "status": STAGE_STATUS_NOT_RUN,
    "failure_type": FAILURE_TYPE_NONE,
    "message": "",
    "basic_info_row_count": 0,
    "all_bond_security_count": 0,
    "price_row_count": 0,
    "price_unique_bond_count": 0,
    "premium_source_row_count": 0,
    "premium_source_unique_bond_count": 0,
    "is_st_source_row_count": 0,
    "is_st_source_unique_underlying_count": 0,
    "redemption_source_row_count": 0,
    "redemption_source_unique_bond_count": 0,
}

SUPPORTABILITY_SUMMARY_TEMPLATE = {
    "status": STAGE_STATUS_NOT_RUN,
    "failure_type": FAILURE_TYPE_NONE,
    "message": "",
    "supportable_row_count": 0,
    "supportable_unique_bond_count": 0,
    "outside_basic_info_row_count": 0,
    "outside_basic_info_unique_bond_count": 0,
    "missing_company_code_legacy_row_count": 0,
    "missing_company_code_legacy_unique_bond_count": 0,
    "unexpected_contract_regression_row_count": 0,
    "unexpected_contract_regression_unique_bond_count": 0,
    "missing_underlying_row_count": 0,
    "missing_underlying_unique_bond_count": 0,
}

PREMIUM_JOIN_SUMMARY_TEMPLATE = {
    "status": STAGE_STATUS_NOT_RUN,
    "failure_type": FAILURE_TYPE_NONE,
    "message": "",
    "premium_joined_row_count": 0,
    "premium_joined_unique_bond_count": 0,
    "missing_premium_row_count": 0,
    "missing_premium_unique_bond_count": 0,
    "missing_premium_ratio": 0.0,
    "premium_missing_ratio_against_active_universe": 0.0,
    "rate_limited_enrichment": False,
    "permission_degraded_enrichment": False,
}

IS_ST_JOIN_SUMMARY_TEMPLATE = {
    "status": STAGE_STATUS_NOT_RUN,
    "failure_type": FAILURE_TYPE_NONE,
    "message": "",
    "is_st_joined_row_count": 0,
    "is_st_joined_unique_bond_count": 0,
    "missing_is_st_row_count": 0,
    "missing_is_st_unique_bond_count": 0,
    "missing_is_st_ratio": 0.0,
}

REDEMPTION_SUMMARY_TEMPLATE = {
    "status": STAGE_STATUS_NOT_RUN,
    "failure_type": FAILURE_TYPE_NONE,
    "message": "",
    "redemption_joined_row_count": 0,
    "redemption_joined_unique_bond_count": 0,
    "missing_redemption_row_count": 0,
    "missing_redemption_unique_bond_count": 0,
    "missing_redemption_ratio": 0.0,
}

VALIDATOR_SUMMARY_TEMPLATE = {
    "status": STAGE_STATUS_NOT_RUN,
    "failure_type": FAILURE_TYPE_NONE,
    "message": "",
    "core_validator_status": STAGE_STATUS_NOT_RUN,
    "core_validator_message": "",
    "enrichment_validator_status": STAGE_STATUS_NOT_RUN,
    "enrichment_validator_message": "",
    "promotion_gate_status": PROMOTION_STATUS_NOT_RUN,
    "promotion_gate_message": "",
}

FINAL_REPORT_TEMPLATE = {
    "execution_mode": EXECUTION_MODE_AUDIT,
    "start_date": "",
    "end_date": "",
    "final_status": FINAL_STATUS_PASS,
    "core_path_status": STAGE_STATUS_NOT_RUN,
    "enrichment_path_status": STAGE_STATUS_NOT_RUN,
    "non_promotion_disclaimer": NON_PROMOTION_DISCLAIMER,
    "active_universe_summary": ACTIVE_UNIVERSE_SUMMARY_TEMPLATE,
    "source_coverage": SOURCE_COVERAGE_TEMPLATE,
    "supportability_summary": SUPPORTABILITY_SUMMARY_TEMPLATE,
    "premium_join_summary": PREMIUM_JOIN_SUMMARY_TEMPLATE,
    "is_st_join_summary": IS_ST_JOIN_SUMMARY_TEMPLATE,
    "redemption_summary": REDEMPTION_SUMMARY_TEMPLATE,
    "validator_summary": VALIDATOR_SUMMARY_TEMPLATE,
    "root_blockers": [],
    "secondary_findings": [],
}

CORE_PATH_STATUS_VALUES = {STAGE_STATUS_PASS, STAGE_STATUS_FAIL, STAGE_STATUS_NOT_RUN}
ENRICHMENT_PATH_STATUS_VALUES = {STAGE_STATUS_PASS, STAGE_STATUS_FAIL, STAGE_STATUS_NOT_RUN, STAGE_STATUS_DEGRADED}
FINAL_STATUS_VALUES = {FINAL_STATUS_PASS, FINAL_STATUS_FAIL_ROOT_BLOCKER, FINAL_STATUS_FAIL_SECONDARY_ONLY}
PROMOTION_GATE_STATUS_VALUES = {PROMOTION_STATUS_PASS, PROMOTION_STATUS_BLOCKED, PROMOTION_STATUS_NOT_RUN}
CORE_VALIDATOR_STATUS_VALUES = {STAGE_STATUS_PASS, STAGE_STATUS_FAIL, STAGE_STATUS_NOT_RUN}

SUMMARY_ENUM_RULES = {
    "source_coverage": {
        "status": {STAGE_STATUS_PASS, STAGE_STATUS_FAIL, STAGE_STATUS_NOT_RUN},
        "failure_type": {FAILURE_TYPE_NONE, "SOURCE_AUTH_FAILURE", "PRICE_SOURCE_UNREADABLE"},
    },
    "supportability_summary": {
        "status": {STAGE_STATUS_PASS, STAGE_STATUS_FAIL, STAGE_STATUS_NOT_RUN},
        "failure_type": {FAILURE_TYPE_NONE, "SUPPORTABILITY_REGRESSION"},
    },
    "premium_join_summary": {
        "status": {STAGE_STATUS_PASS, STAGE_STATUS_FAIL, STAGE_STATUS_NOT_RUN, STAGE_STATUS_DEGRADED},
        "failure_type": {
            FAILURE_TYPE_NONE,
            "PREMIUM_SOURCE_TRUNCATION",
            "PREMIUM_RATE_MISSING_BROAD_COVERAGE",
            "RATE_LIMITED_ENRICHMENT",
            "PERMISSION_DEGRADED_ENRICHMENT",
        },
    },
    "is_st_join_summary": {
        "status": {STAGE_STATUS_PASS, STAGE_STATUS_FAIL, STAGE_STATUS_NOT_RUN, STAGE_STATUS_DEGRADED},
        "failure_type": {FAILURE_TYPE_NONE, "IS_ST_SOURCE_GAP", "PERMISSION_DEGRADED_ENRICHMENT"},
    },
    "redemption_summary": {
        "status": {STAGE_STATUS_PASS, STAGE_STATUS_FAIL, STAGE_STATUS_NOT_RUN, STAGE_STATUS_DEGRADED},
        "failure_type": {FAILURE_TYPE_NONE, "REDEMPTION_SOURCE_GAP", "PERMISSION_DEGRADED_ENRICHMENT"},
    },
    "validator_summary": {
        "status": {STAGE_STATUS_PASS, STAGE_STATUS_FAIL, STAGE_STATUS_NOT_RUN, STAGE_STATUS_DEGRADED},
        "failure_type": {FAILURE_TYPE_NONE, "VALIDATOR_SCHEMA_FAILURE", "VALIDATOR_SEMANTIC_FAILURE"},
        "core_validator_status": CORE_VALIDATOR_STATUS_VALUES,
        "enrichment_validator_status": ENRICHMENT_PATH_STATUS_VALUES,
        "promotion_gate_status": PROMOTION_GATE_STATUS_VALUES,
    },
}


def _apply(template: dict, overrides: dict | None = None) -> dict:
    data = deepcopy(template)
    if overrides:
        for key, value in overrides.items():
            if key in data:
                data[key] = value
    return data


def _validate_enum(field_name: str, value: str, allowed: set[str]) -> None:
    if value not in allowed:
        allowed_values = "|".join(sorted(allowed))
        raise ValueError(f"Invalid {field_name}: {value!r}. Allowed: {allowed_values}")


def _normalize_trigger(trigger: object) -> str:
    if trigger is None:
        return ""
    if isinstance(trigger, str):
        return trigger
    return str(trigger)


def _validate_item_schema(item_name: str, item: dict, *, allowed_types: set[str], allowed_stages: set[str]) -> None:
    expected_keys = {"type", "stage", "trigger", "evidence"}
    if set(item.keys()) != expected_keys:
        raise ValueError(f"Invalid {item_name} keys: {sorted(item.keys())}. Expected: {sorted(expected_keys)}")
    _validate_enum(f"{item_name}.type", item["type"], allowed_types)
    _validate_enum(f"{item_name}.stage", item["stage"], allowed_stages)
    if not isinstance(item["trigger"], str):
        raise ValueError(f"Invalid {item_name}.trigger type: expected str")
    if not isinstance(item["evidence"], dict):
        raise ValueError(f"Invalid {item_name}.evidence type: expected dict")


def _validate_summary(summary_name: str, data: dict) -> dict:
    for field_name, allowed_values in SUMMARY_ENUM_RULES.get(summary_name, {}).items():
        _validate_enum(f"{summary_name}.{field_name}", data[field_name], allowed_values)
    return data


def _build_summary(template: dict, summary_name: str, overrides: dict | None = None) -> dict:
    data = _apply(template, overrides)
    return _validate_summary(summary_name, data)


def build_active_universe_summary(**overrides) -> dict:
    return _apply(ACTIVE_UNIVERSE_SUMMARY_TEMPLATE, overrides)


def build_source_coverage(**overrides) -> dict:
    return _build_summary(SOURCE_COVERAGE_TEMPLATE, "source_coverage", overrides)


def build_supportability_summary(**overrides) -> dict:
    return _build_summary(SUPPORTABILITY_SUMMARY_TEMPLATE, "supportability_summary", overrides)


def build_premium_join_summary(**overrides) -> dict:
    return _build_summary(PREMIUM_JOIN_SUMMARY_TEMPLATE, "premium_join_summary", overrides)


def build_is_st_join_summary(**overrides) -> dict:
    return _build_summary(IS_ST_JOIN_SUMMARY_TEMPLATE, "is_st_join_summary", overrides)


def build_redemption_summary(**overrides) -> dict:
    return _build_summary(REDEMPTION_SUMMARY_TEMPLATE, "redemption_summary", overrides)


def build_validator_summary(**overrides) -> dict:
    return _build_summary(VALIDATOR_SUMMARY_TEMPLATE, "validator_summary", overrides)


def build_pipeline_results() -> dict:
    return {
        "source_coverage": build_source_coverage(),
        "supportability_summary": build_supportability_summary(),
        "premium_join_summary": build_premium_join_summary(),
        "is_st_join_summary": build_is_st_join_summary(),
        "redemption_summary": build_redemption_summary(),
        "validator_summary": build_validator_summary(),
        "active_universe_summary": build_active_universe_summary(),
    }


def build_root_blocker(blocker_type: str, stage: str, trigger: str = "", evidence: dict | None = None) -> dict:
    blocker = {
        "type": blocker_type,
        "stage": stage,
        "trigger": _normalize_trigger(trigger),
        "evidence": evidence or {},
    }
    _validate_item_schema(
        "root_blockers[]",
        blocker,
        allowed_types=ROOT_BLOCKER_TYPES,
        allowed_stages=ROOT_BLOCKER_STAGES,
    )
    return blocker


def build_secondary_finding(finding_type: str, stage: str, trigger: str = "", evidence: dict | None = None) -> dict:
    finding = {
        "type": finding_type,
        "stage": stage,
        "trigger": _normalize_trigger(trigger),
        "evidence": evidence or {},
    }
    _validate_item_schema(
        "secondary_findings[]",
        finding,
        allowed_types=SECONDARY_FINDING_TYPES,
        allowed_stages=SECONDARY_FINDING_STAGES,
    )
    return finding


def _validate_report(report: dict) -> dict:
    expected_keys = set(FINAL_REPORT_TEMPLATE.keys())
    if set(report.keys()) != expected_keys:
        raise ValueError(f"Invalid final report keys: {sorted(report.keys())}. Expected: {sorted(expected_keys)}")

    if report["execution_mode"] != EXECUTION_MODE_AUDIT:
        raise ValueError(f"Invalid execution_mode: {report['execution_mode']!r}")
    if report["non_promotion_disclaimer"] != NON_PROMOTION_DISCLAIMER:
        raise ValueError(f"Invalid non_promotion_disclaimer: {report['non_promotion_disclaimer']!r}")

    _validate_enum("final_status", report["final_status"], FINAL_STATUS_VALUES)
    _validate_enum("core_path_status", report["core_path_status"], CORE_PATH_STATUS_VALUES)
    _validate_enum("enrichment_path_status", report["enrichment_path_status"], ENRICHMENT_PATH_STATUS_VALUES)

    build_active_universe_summary(**report["active_universe_summary"])
    build_source_coverage(**report["source_coverage"])
    build_supportability_summary(**report["supportability_summary"])
    build_premium_join_summary(**report["premium_join_summary"])
    build_is_st_join_summary(**report["is_st_join_summary"])
    build_redemption_summary(**report["redemption_summary"])
    build_validator_summary(**report["validator_summary"])

    for blocker in report["root_blockers"]:
        _validate_item_schema(
            "root_blockers[]",
            blocker,
            allowed_types=ROOT_BLOCKER_TYPES,
            allowed_stages=ROOT_BLOCKER_STAGES,
        )
    for finding in report["secondary_findings"]:
        _validate_item_schema(
            "secondary_findings[]",
            finding,
            allowed_types=SECONDARY_FINDING_TYPES,
            allowed_stages=SECONDARY_FINDING_STAGES,
        )

    return report


def build_final_report(
    *,
    start_date: str,
    end_date: str,
    final_status: str,
    core_path_status: str,
    enrichment_path_status: str,
    results: dict,
    root_blockers: list[dict],
    secondary_findings: list[dict],
) -> dict:
    report = _apply(
        FINAL_REPORT_TEMPLATE,
        {
            "start_date": start_date,
            "end_date": end_date,
            "final_status": final_status,
            "core_path_status": core_path_status,
            "enrichment_path_status": enrichment_path_status,
            "root_blockers": list(root_blockers),
            "secondary_findings": list(secondary_findings),
        },
    )
    report["active_universe_summary"] = build_active_universe_summary(**results.get("active_universe_summary", {}))
    report["source_coverage"] = build_source_coverage(**results.get("source_coverage", {}))
    report["supportability_summary"] = build_supportability_summary(**results.get("supportability_summary", {}))
    report["premium_join_summary"] = build_premium_join_summary(**results.get("premium_join_summary", {}))
    report["is_st_join_summary"] = build_is_st_join_summary(**results.get("is_st_join_summary", {}))
    report["redemption_summary"] = build_redemption_summary(**results.get("redemption_summary", {}))
    report["validator_summary"] = build_validator_summary(**results.get("validator_summary", {}))
    return _validate_report(report)
