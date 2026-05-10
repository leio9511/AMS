from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from etl.cb_audit_contract import JQDATA_CONVERT_PRICE_PROVENANCE

FIELD_LAYER_CORE = "core"
FIELD_LAYER_ENRICHMENT = "enrichment"
VALIDATOR_SCOPE_CORE = "core"
VALIDATOR_SCOPE_ENRICHMENT = "enrichment"

# Wave 1 redemption semantic split contract:
# - redeem_risk = trading-risk window field used by strategy/risk filtering
# - is_redeemed = terminal/delist state derived from redemption source contract
# The two fields are intentionally separate so the system can represent
# redeem_risk=True while is_redeemed=False during the pre-delist risk window.

TUSHARE_CONVERT_PRICE_PROVENANCE_LATEST = "latest_non_null_convertprice_aft"
TUSHARE_CONVERT_PRICE_PROVENANCE_INITIAL = "convert_price_initial"
TUSHARE_CONVERT_PRICE_PROVENANCE_BASIC = "cb_basic.conv_price"
TUSHARE_CONVERT_PRICE_PROVENANCES = {
    TUSHARE_CONVERT_PRICE_PROVENANCE_LATEST,
    TUSHARE_CONVERT_PRICE_PROVENANCE_INITIAL,
    TUSHARE_CONVERT_PRICE_PROVENANCE_BASIC,
}


@dataclass(frozen=True)
class GovernedField:
    name: str
    layer: Literal["core", "enrichment"]
    source_semantics: str
    fallback_semantics: str
    validator_scope: Literal["core", "enrichment"]
    degraded_behavior: str
    promotion_sensitive: bool
    derived_formula: str | None = None


FIELD_REGISTRY: dict[str, GovernedField] = {
    "ticker": GovernedField(
        name="ticker",
        layer=FIELD_LAYER_CORE,
        source_semantics="Canonical full bond ticker from provider daily price path.",
        fallback_semantics="No fallback; core path fails if missing.",
        validator_scope=VALIDATOR_SCOPE_CORE,
        degraded_behavior="Not degradable.",
        promotion_sensitive=True,
    ),
    "date": GovernedField(
        name="date",
        layer=FIELD_LAYER_CORE,
        source_semantics="Canonical trading date for the active price row.",
        fallback_semantics="No fallback; core path fails if missing.",
        validator_scope=VALIDATOR_SCOPE_CORE,
        degraded_behavior="Not degradable.",
        promotion_sensitive=True,
    ),
    "open": GovernedField(
        name="open",
        layer=FIELD_LAYER_CORE,
        source_semantics="Provider daily OHLCV open on active price rows.",
        fallback_semantics="No fallback; active-universe filter removes all-null OHLCV rows before validation.",
        validator_scope=VALIDATOR_SCOPE_CORE,
        degraded_behavior="Not degradable on active rows.",
        promotion_sensitive=True,
    ),
    "high": GovernedField(
        name="high",
        layer=FIELD_LAYER_CORE,
        source_semantics="Provider daily OHLCV high on active price rows.",
        fallback_semantics="No fallback; active-universe filter removes all-null OHLCV rows before validation.",
        validator_scope=VALIDATOR_SCOPE_CORE,
        degraded_behavior="Not degradable on active rows.",
        promotion_sensitive=True,
    ),
    "low": GovernedField(
        name="low",
        layer=FIELD_LAYER_CORE,
        source_semantics="Provider daily OHLCV low on active price rows.",
        fallback_semantics="No fallback; active-universe filter removes all-null OHLCV rows before validation.",
        validator_scope=VALIDATOR_SCOPE_CORE,
        degraded_behavior="Not degradable on active rows.",
        promotion_sensitive=True,
    ),
    "close": GovernedField(
        name="close",
        layer=FIELD_LAYER_CORE,
        source_semantics="Provider daily OHLCV close on active price rows.",
        fallback_semantics="No fallback; core validator requires close > 0.",
        validator_scope=VALIDATOR_SCOPE_CORE,
        degraded_behavior="Not degradable on active rows.",
        promotion_sensitive=True,
    ),
    "volume": GovernedField(
        name="volume",
        layer=FIELD_LAYER_CORE,
        source_semantics="Provider daily OHLCV volume on active price rows.",
        fallback_semantics="No fallback; active-universe filter removes all-null OHLCV rows before validation.",
        validator_scope=VALIDATOR_SCOPE_CORE,
        degraded_behavior="Not degradable on active rows.",
        promotion_sensitive=True,
    ),
    "underlying_ticker": GovernedField(
        name="underlying_ticker",
        layer=FIELD_LAYER_CORE,
        source_semantics="Security-master mapping from bond basic info to canonical underlying stock ticker.",
        fallback_semantics="No fallback; supportability regression if missing for supportable bonds.",
        validator_scope=VALIDATOR_SCOPE_CORE,
        degraded_behavior="Not degradable for supportable rows.",
        promotion_sensitive=True,
    ),
    "is_st": GovernedField(
        name="is_st",
        layer=FIELD_LAYER_CORE,
        source_semantics="Provider ST status joined by canonical underlying_ticker and date.",
        fallback_semantics="No synthetic fallback; source gaps are reported explicitly.",
        validator_scope=VALIDATOR_SCOPE_CORE,
        degraded_behavior="Core path failure if unavailable for supportable rows.",
        promotion_sensitive=True,
    ),
    "redeem_risk": GovernedField(
        name="redeem_risk",
        layer=FIELD_LAYER_CORE,
        source_semantics=(
            "Trading-risk redemption window field consumed by strategy filtering "
            "before terminal-state filtering; may be True while is_redeemed remains False."
        ),
        fallback_semantics=(
            "Wave 1 transitional default is redeem_risk=False unless an explicit controlled "
            "fixture/source sets the trading-risk window state."
        ),
        validator_scope=VALIDATOR_SCOPE_CORE,
        degraded_behavior="Deterministic placeholder/default population is allowed while upstream sourcing remains transitional.",
        promotion_sensitive=True,
    ),
    "is_redeemed": GovernedField(
        name="is_redeemed",
        layer=FIELD_LAYER_CORE,
        source_semantics=(
            "Terminal/delist redemption state derived from the governed delist_Date source contract; "
            "it is not the trading-risk window field."
        ),
        fallback_semantics="Null primary behavior is is_redeemed=False per redemption contract.",
        validator_scope=VALIDATOR_SCOPE_CORE,
        degraded_behavior="Core path failure if the source contract regresses.",
        promotion_sensitive=True,
    ),
    "premium_rate": GovernedField(
        name="premium_rate",
        layer=FIELD_LAYER_ENRICHMENT,
        source_semantics="Canonical premium rate normalized from provider daily premium output or governed TuShare reconstruction.",
        fallback_semantics="JQData uses provider-supplied convert_premium_rate; TuShare reconstructs from governed convert_price fallback order.",
        validator_scope=VALIDATOR_SCOPE_ENRICHMENT,
        degraded_behavior="May be degraded by rate limit, permission, or source coverage gaps.",
        promotion_sensitive=True,
    ),
    "double_low": GovernedField(
        name="double_low",
        layer=FIELD_LAYER_ENRICHMENT,
        source_semantics="Canonical derived enrichment field.",
        fallback_semantics="Always derived from close + premium_rate * 100; never sourced independently.",
        validator_scope=VALIDATOR_SCOPE_ENRICHMENT,
        degraded_behavior="Missing whenever premium_rate is unavailable.",
        promotion_sensitive=True,
        derived_formula="close + premium_rate * 100",
    ),
    "convert_price": GovernedField(
        name="convert_price",
        layer=FIELD_LAYER_ENRICHMENT,
        source_semantics="Effective conversion price preserved from provider daily premium payload or governed TuShare fallback winner.",
        fallback_semantics=(
            "JQData: provider-supplied CONBOND_DAILY_CONVERT.convert_price. "
            "TuShare fallback order: latest non-null convertprice_aft -> convert_price_initial -> cb_basic.conv_price -> missing."
        ),
        validator_scope=VALIDATOR_SCOPE_ENRICHMENT,
        degraded_behavior="May be null when governed fallback order exhausts all candidates.",
        promotion_sensitive=False,
    ),
    "convert_price_provenance": GovernedField(
        name="convert_price_provenance",
        layer=FIELD_LAYER_ENRICHMENT,
        source_semantics="Machine-readable provenance describing which governed source supplied convert_price.",
        fallback_semantics=(
            f"Allowed governed values include {JQDATA_CONVERT_PRICE_PROVENANCE}, "
            f"{TUSHARE_CONVERT_PRICE_PROVENANCE_LATEST}, {TUSHARE_CONVERT_PRICE_PROVENANCE_INITIAL}, "
            f"and {TUSHARE_CONVERT_PRICE_PROVENANCE_BASIC}."
        ),
        validator_scope=VALIDATOR_SCOPE_ENRICHMENT,
        degraded_behavior="Null when convert_price is missing.",
        promotion_sensitive=False,
    ),
}

CORE_FIELDS: list[str] = [
    name for name, spec in FIELD_REGISTRY.items() if spec.layer == FIELD_LAYER_CORE
]
ENRICHMENT_FIELDS: list[str] = [
    name for name, spec in FIELD_REGISTRY.items() if spec.layer == FIELD_LAYER_ENRICHMENT
]
CANONICAL_CB_COLUMNS: list[str] = CORE_FIELDS + ENRICHMENT_FIELDS
CORE_VALIDATOR_COLUMNS: list[str] = [
    name for name, spec in FIELD_REGISTRY.items() if spec.validator_scope == VALIDATOR_SCOPE_CORE
]
ENRICHMENT_VALIDATOR_COLUMNS: list[str] = [
    name for name, spec in FIELD_REGISTRY.items() if spec.validator_scope == VALIDATOR_SCOPE_ENRICHMENT
]
GOVERNED_PREMIUM_JOIN_COLUMNS: list[str] = [
    "premium_rate",
    "convert_price",
    "convert_price_provenance",
]


def get_field(name: str) -> GovernedField:
    return FIELD_REGISTRY[name]
