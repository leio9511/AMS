from ams.utils.provider_config import resolve_provider_dataset_path, get_provider_artifact_paths
import etl.jqdata_sync_cb
import json
import os
import unittest
from unittest.mock import patch

import pandas as pd

from etl.jqdata_sync_cb import sync_cb_data
from etl.cb_etl_pipeline import CBETLPipeline, SUPPORTABILITY_BUCKET_SUPPORTABLE


class TestJQDataSyncCBLogic(unittest.TestCase):
    def setUp(self):
        self.start_date = "2024-01-01"
        self.end_date = "2024-01-05"
        self.ticker = "123456.XSHG"
        self.raw_code = "123456"
        self.exchange_code = "XSHG"
        self.underlying = "600000.XSHG"

    def _mock_bonds_info(self, delist_date="2024-12-31"):
        return pd.DataFrame(
            {
                "code": [self.raw_code],
                "company_code": [self.underlying],
                "delist_Date": [delist_date],
            }
        )

    def _single_price_df(self, date_str: str) -> pd.DataFrame:
        return pd.DataFrame(
            {"open": [100.0], "high": [101.0], "low": [99.0], "close": [100.0], "volume": [1000]},
            index=pd.MultiIndex.from_tuples([(pd.to_datetime(date_str), self.ticker)], names=["time", "code"]),
        )

    @patch("etl.jqdata_sync_cb.jqdatasdk")
    @patch("ams.validators.cb_data_validator.DatasetSemanticValidator")
    @patch("ams.validators.cb_data_validator.CBDataValidator")
    def test_fetch_real_premium_rate(self, mock_validator, mock_semantic_validator, mock_jq):
        mock_semantic_validator.return_value.validate_dataframe.return_value = True
        os.environ["JQDATA_USER"] = "test"
        os.environ["JQDATA_PWD"] = "test"
        mock_jq.auth.return_value = None
        mock_jq.get_all_securities.return_value = pd.DataFrame(index=[self.ticker])
        mock_jq.get_security_info.side_effect = AssertionError("legacy get_security_info path must not be used")

        mock_jq.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True

        price_data = pd.DataFrame(
            {
                "open": [100.0] * 5,
                "high": [101.0] * 5,
                "low": [99.0] * 5,
                "close": [100.0] * 5,
                "volume": [1000] * 5,
            },
            index=pd.MultiIndex.from_product(
                [pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]), [self.ticker]],
                names=["time", "code"],
            ),
        )
        mock_jq.get_price.return_value = price_data

        premium_data = pd.DataFrame(
            {
                "date": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"],
                "code": [self.raw_code] * 5,
                "exchange_code": [self.exchange_code] * 5,
                "convert_premium_rate": [10.0, 15.0, 20.0, 25.0, 30.0],
            }
        )
        mock_jq.bond.run_query.side_effect = [self._mock_bonds_info(), premium_data]
        mock_jq.get_extras.return_value = pd.DataFrame(
            {self.underlying: [False, False, True, True, False]},
            index=pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]),
        )
        mock_validator.return_value.validate_dataframe.return_value = True

        sync_cb_data(self.start_date, self.end_date)

        df = pd.read_csv(resolve_provider_dataset_path("jqdata"))
        self.assertTrue((df["premium_rate"] > 0).all())
        self.assertEqual(df["premium_rate"].iloc[0], 0.1)
        self.assertEqual(df["premium_rate"].iloc[4], 0.3)
        self.assertEqual(df["underlying_ticker"].iloc[0], self.underlying)

    @patch("etl.jqdata_sync_cb.jqdatasdk")
    @patch("ams.validators.cb_data_validator.DatasetSemanticValidator")
    @patch("ams.validators.cb_data_validator.CBDataValidator")
    def test_sync_cb_data_uses_company_code_when_basic_info_is_available(self, mock_validator, mock_semantic_validator, mock_jq):
        mock_semantic_validator.return_value.validate_dataframe.return_value = True
        os.environ["JQDATA_USER"] = "test"
        os.environ["JQDATA_PWD"] = "test"
        mock_jq.auth.return_value = None
        mock_jq.get_all_securities.return_value = pd.DataFrame(index=[self.ticker])
        mock_jq.get_security_info.side_effect = AssertionError("legacy get_security_info path must not be used")

        mock_jq.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True
        mock_jq.get_price.return_value = self._single_price_df("2024-01-03")

        premium = pd.DataFrame(
            {"date": ["2024-01-03"], "code": [self.raw_code], "exchange_code": [self.exchange_code], "convert_premium_rate": [10.0]}
        )
        mock_jq.bond.run_query.side_effect = [self._mock_bonds_info(), premium]
        mock_jq.get_extras.return_value = pd.DataFrame({self.underlying: [True]}, index=pd.to_datetime(["2024-01-03"]))
        mock_validator.return_value.validate_dataframe.return_value = True

        sync_cb_data("2024-01-03", "2024-01-03")

        df = pd.read_csv(resolve_provider_dataset_path("jqdata"))
        self.assertEqual(df["underlying_ticker"].iloc[0], self.underlying)
        self.assertTrue(df["is_st"].iloc[0])

    @patch("etl.jqdata_sync_cb.jqdatasdk")
    @patch("ams.validators.cb_data_validator.DatasetSemanticValidator")
    @patch("ams.validators.cb_data_validator.CBDataValidator")
    def test_sync_cb_data_maps_underlying_ticker_from_bond_code_raw(self, mock_validator, mock_semantic_validator, mock_jq):
        mock_semantic_validator.return_value.validate_dataframe.return_value = True
        os.environ["JQDATA_USER"] = "test"
        os.environ["JQDATA_PWD"] = "test"
        mock_jq.auth.return_value = None
        mock_jq.get_all_securities.return_value = pd.DataFrame(index=[self.ticker])
        mock_jq.get_security_info.side_effect = AssertionError("legacy get_security_info path must not be used")

        mock_jq.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True
        mock_jq.get_price.return_value = self._single_price_df("2024-01-03")

        premium = pd.DataFrame(
            {"date": ["2024-01-03"], "code": [self.raw_code], "exchange_code": [self.exchange_code], "convert_premium_rate": [10.0]}
        )
        mock_jq.bond.run_query.side_effect = [self._mock_bonds_info(), premium]
        mock_jq.get_extras.return_value = pd.DataFrame({self.underlying: [False]}, index=pd.to_datetime(["2024-01-03"]))
        mock_validator.return_value.validate_dataframe.return_value = True

        sync_cb_data("2024-01-03", "2024-01-03")

        df = pd.read_csv(resolve_provider_dataset_path("jqdata"))
        queried_raw_codes = mock_jq.bond.CONBOND_DAILY_CONVERT.code.in_.call_args.args[0]
        self.assertEqual(queried_raw_codes, [self.raw_code])
        self.assertEqual(df["underlying_ticker"].iloc[0], self.underlying)

    @patch("etl.jqdata_sync_cb.jqdatasdk")
    @patch("ams.validators.cb_data_validator.DatasetSemanticValidator")
    @patch("ams.validators.cb_data_validator.CBDataValidator")
    def test_sync_cb_data_populates_premium_rate_from_normalized_daily_convert_join(self, mock_validator, mock_semantic_validator, mock_jq):
        mock_semantic_validator.return_value.validate_dataframe.return_value = True
        os.environ["JQDATA_USER"] = "test"
        os.environ["JQDATA_PWD"] = "test"
        mock_jq.auth.return_value = None
        mock_jq.get_all_securities.return_value = pd.DataFrame(index=["123071.XSHE"])
        mock_jq.get_security_info.side_effect = AssertionError("legacy get_security_info path must not be used")

        mock_jq.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True

        mock_jq.get_price.return_value = pd.DataFrame(
            {"open": [100.0], "high": [101.0], "low": [99.0], "close": [100.0], "volume": [1000]},
            index=pd.MultiIndex.from_tuples([(pd.to_datetime("2024-01-03"), "123071.XSHE")], names=["time", "code"]),
        )

        bonds_info = pd.DataFrame({"code": ["123071"], "company_code": ["000001.XSHE"], "delist_Date": ["2024-12-31"]})
        premium = pd.DataFrame({"date": ["2024-01-03"], "code": ["123071"], "exchange_code": ["XSHE"], "convert_premium_rate": [15.5]})
        mock_jq.bond.run_query.side_effect = [bonds_info, premium]
        mock_jq.get_extras.return_value = pd.DataFrame({"000001.XSHE": [False]}, index=pd.to_datetime(["2024-01-03"]))
        mock_validator.return_value.validate_dataframe.return_value = True

        sync_cb_data("2024-01-03", "2024-01-03")

        df = pd.read_csv(resolve_provider_dataset_path("jqdata"))
        self.assertEqual(df["premium_rate"].iloc[0], 0.155)
        with open(get_provider_artifact_paths("jqdata")["metrics_path"], "r", encoding="utf-8") as f:
            metrics = json.load(f)
        self.assertEqual(metrics["premium_rate_source_row_count"], 1)
        self.assertEqual(metrics["premium_rate_joined_row_count"], 1)
        self.assertEqual(metrics["premium_rate_join_coverage_ratio"], 1.0)

    @patch("etl.jqdata_sync_cb.jqdatasdk")
    @patch("ams.validators.cb_data_validator.DatasetSemanticValidator")
    @patch("ams.validators.cb_data_validator.CBDataValidator")
    def test_sync_cb_data_uses_basic_info_delist_date_for_redemption_semantics(self, mock_validator, mock_semantic_validator, mock_jq):
        mock_semantic_validator.return_value.validate_dataframe.return_value = True
        os.environ["JQDATA_USER"] = "test"
        os.environ["JQDATA_PWD"] = "test"
        mock_jq.auth.return_value = None
        mock_jq.get_all_securities.return_value = pd.DataFrame(index=[self.ticker])
        mock_jq.get_security_info.side_effect = AssertionError("legacy get_security_info path must not be used")

        mock_jq.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True
        mock_jq.get_price.return_value = self._single_price_df("2024-04-30")

        premium = pd.DataFrame(
            {"date": ["2024-04-30"], "code": [self.raw_code], "exchange_code": [self.exchange_code], "convert_premium_rate": [10.0]}
        )
        mock_jq.bond.run_query.side_effect = [self._mock_bonds_info("2024-04-30"), premium]
        mock_jq.get_extras.return_value = pd.DataFrame({self.underlying: [False]}, index=pd.to_datetime(["2024-04-30"]))
        mock_validator.return_value.validate_dataframe.return_value = True

        sync_cb_data("2024-04-30", "2024-04-30")

        df = pd.read_csv(resolve_provider_dataset_path("jqdata"))
        self.assertTrue(df["is_redeemed"].iloc[0])
        with open(get_provider_artifact_paths("jqdata")["metrics_path"], "r", encoding="utf-8") as f:
            metrics = json.load(f)
        self.assertEqual(metrics["is_redeemed_missing_delist_count"], 0)

    @patch("etl.jqdata_sync_cb.jqdatasdk")
    @patch("ams.validators.cb_data_validator.DatasetSemanticValidator")
    @patch("ams.validators.cb_data_validator.CBDataValidator")
    def test_supportability_filtering_happens_before_premium_and_st_joins(
        self, mock_validator, mock_semantic_validator, mock_jq
    ):
        mock_semantic_validator.return_value.validate_dataframe.return_value = True
        os.environ["JQDATA_USER"] = "test"
        os.environ["JQDATA_PWD"] = "test"
        mock_jq.auth.return_value = None
        mock_jq.get_all_securities.return_value = pd.DataFrame(
            index=["123456.XSHG", "654321.XSHG", "999999.XSHG"]
        )
        mock_jq.get_security_info.side_effect = AssertionError("legacy get_security_info path must not be used")

        mock_jq.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True
        mock_jq.get_price.return_value = pd.DataFrame(
            {
                "open": [100.0, 101.0, 102.0],
                "high": [101.0, 102.0, 103.0],
                "low": [99.0, 100.0, 101.0],
                "close": [100.0, 101.0, 102.0],
                "volume": [1000, 1100, 1200],
            },
            index=pd.MultiIndex.from_tuples(
                [
                    (pd.to_datetime("2025-01-17"), "123456.XSHG"),
                    (pd.to_datetime("2025-01-17"), "654321.XSHG"),
                    (pd.to_datetime("2025-01-17"), "999999.XSHG"),
                ],
                names=["time", "code"],
            ),
        )

        mock_jq.bond.run_query.side_effect = [
            pd.DataFrame(
                {
                    "code": ["123456", "654321"],
                    "company_code": ["600000.XSHG", None],
                    "delist_Date": ["2026-12-31", "2004-01-01"],
                }
            ),
            pd.DataFrame(
                {
                    "date": ["2025-01-17"],
                    "code": ["123456"],
                    "exchange_code": ["XSHG"],
                    "convert_premium_rate": [10.0],
                }
            ),
        ]
        mock_jq.get_extras.return_value = pd.DataFrame(
            {"600000.XSHG": [False]}, index=pd.to_datetime(["2025-01-17"])
        )
        mock_validator.return_value.validate_dataframe.return_value = True

        sync_cb_data("2025-01-17", "2025-01-17")

        queried_raw_codes = mock_jq.bond.CONBOND_DAILY_CONVERT.code.in_.call_args.args[0]
        self.assertEqual(queried_raw_codes, ["123456"])
        get_extras_args, get_extras_kwargs = mock_jq.get_extras.call_args
        self.assertEqual(get_extras_args[0], "is_st")
        self.assertEqual(get_extras_args[1], ["600000.XSHG"])
        self.assertEqual(get_extras_kwargs["start_date"], "2025-01-17")
        self.assertEqual(get_extras_kwargs["end_date"], "2025-01-17")

        df = pd.read_csv(resolve_provider_dataset_path("jqdata"))
        self.assertEqual(df["ticker"].tolist(), ["123456.XSHG"])

        with open(get_provider_artifact_paths("jqdata")["metrics_path"], "r", encoding="utf-8") as f:
            metrics = json.load(f)
        self.assertEqual(metrics["filtered_bond_codes_outside_basic_info"], ["999999"])
        self.assertEqual(metrics["filtered_bond_codes_missing_company_code_legacy"], ["654321"])

    @patch("etl.jqdata_sync_cb.jqdatasdk")
    @patch("ams.validators.cb_data_validator.DatasetSemanticValidator")
    @patch("ams.validators.cb_data_validator.CBDataValidator")
    def test_fetch_st_status(self, mock_validator, mock_semantic_validator, mock_jq):
        mock_semantic_validator.return_value.validate_dataframe.return_value = True
        os.environ["JQDATA_USER"] = "test"
        os.environ["JQDATA_PWD"] = "test"
        mock_jq.auth.return_value = None
        mock_jq.get_all_securities.return_value = pd.DataFrame(index=[self.ticker])
        mock_jq.get_security_info.side_effect = AssertionError("legacy get_security_info path must not be used")

        mock_jq.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True
        mock_jq.get_price.return_value = self._single_price_df("2024-01-03")

        mock_jq.bond.run_query.side_effect = [
            self._mock_bonds_info(),
            pd.DataFrame({"date": ["2024-01-03"], "code": [self.raw_code], "exchange_code": [self.exchange_code], "convert_premium_rate": [10.0]}),
        ]
        mock_jq.get_extras.return_value = pd.DataFrame({self.underlying: [True]}, index=pd.to_datetime(["2024-01-03"]))
        mock_validator.return_value.validate_dataframe.return_value = True

        sync_cb_data("2024-01-03", "2024-01-03")

        df = pd.read_csv(resolve_provider_dataset_path("jqdata"))
        self.assertTrue(df["is_st"].iloc[0])

    @patch("etl.jqdata_sync_cb.jqdatasdk")
    @patch("ams.validators.cb_data_validator.DatasetSemanticValidator")
    @patch("ams.validators.cb_data_validator.CBDataValidator")
    def test_etl_fail_fast_on_missing_premium(self, mock_validator, mock_semantic_validator, mock_jq):
        os.environ["JQDATA_USER"] = "test"
        os.environ["JQDATA_PWD"] = "test"
        mock_jq.auth.return_value = None
        mock_jq.get_all_securities.return_value = pd.DataFrame(index=[self.ticker])
        mock_jq.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True
        mock_jq.get_price.return_value = self._single_price_df("2024-01-03")

        mock_jq.bond.run_query.side_effect = [self._mock_bonds_info(), pd.DataFrame()]
        mock_jq.get_extras.return_value = pd.DataFrame({self.underlying: [True]}, index=pd.to_datetime(["2024-01-03"]))

        with self.assertRaises((ValueError, SystemExit)):
            sync_cb_data("2024-01-03", "2024-01-03")

    @patch("etl.jqdata_sync_cb.jqdatasdk")
    @patch("ams.validators.cb_data_validator.DatasetSemanticValidator")
    @patch("ams.validators.cb_data_validator.CBDataValidator")
    def test_etl_fail_fast_on_missing_is_st(self, mock_validator, mock_semantic_validator, mock_jq):
        os.environ["JQDATA_USER"] = "test"
        os.environ["JQDATA_PWD"] = "test"
        mock_jq.auth.return_value = None
        mock_jq.get_all_securities.return_value = pd.DataFrame(index=[self.ticker])
        mock_jq.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True
        mock_jq.get_price.return_value = self._single_price_df("2024-01-03")

        premium = pd.DataFrame({"date": ["2024-01-03"], "code": [self.raw_code], "exchange_code": [self.exchange_code], "convert_premium_rate": [10.0]})
        mock_jq.bond.run_query.side_effect = [self._mock_bonds_info(), premium]
        mock_jq.get_extras.return_value = pd.DataFrame()

        with self.assertRaises((ValueError, SystemExit)):
            sync_cb_data("2024-01-03", "2024-01-03")

    @patch("etl.jqdata_sync_cb.jqdatasdk")
    @patch("ams.validators.cb_data_validator.DatasetSemanticValidator")
    @patch("ams.validators.cb_data_validator.CBDataValidator")
    def test_etl_promotion_success(self, mock_validator, mock_semantic_validator, mock_jq):
        os.environ["JQDATA_USER"] = "test"
        os.environ["JQDATA_PWD"] = "test"
        mock_jq.auth.return_value = None
        mock_jq.get_all_securities.return_value = pd.DataFrame(index=[self.ticker])
        mock_jq.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True
        mock_jq.get_price.return_value = self._single_price_df("2024-01-03")
        premium = pd.DataFrame({"date": ["2024-01-03"], "code": [self.raw_code], "exchange_code": [self.exchange_code], "convert_premium_rate": [10.0]})
        mock_jq.bond.run_query.side_effect = [self._mock_bonds_info(), premium]
        mock_jq.get_extras.return_value = pd.DataFrame({self.underlying: [True]}, index=pd.to_datetime(["2024-01-03"]))

        mock_validator.return_value.validate_dataframe.return_value = True
        mock_semantic_validator.return_value.validate_dataframe.return_value = True

        with patch("os.replace") as mock_replace:
            sync_cb_data("2024-01-03", "2024-01-03")

            calls = [call for call in mock_replace.mock_calls if "cb_history_factors.csv.tmp" in str(call)]
            self.assertTrue(len(calls) > 0)

    @patch("etl.jqdata_sync_cb.jqdatasdk")
    @patch("ams.validators.cb_data_validator.DatasetSemanticValidator")
    @patch("ams.validators.cb_data_validator.CBDataValidator")
    def test_etl_validation_failure_blocks_promotion(self, mock_validator, mock_semantic_validator, mock_jq):
        os.environ["JQDATA_USER"] = "test"
        os.environ["JQDATA_PWD"] = "test"
        mock_jq.auth.return_value = None
        mock_jq.get_all_securities.return_value = pd.DataFrame(index=[self.ticker])
        mock_jq.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True
        mock_jq.get_price.return_value = self._single_price_df("2024-01-03")
        premium = pd.DataFrame({"date": ["2024-01-03"], "code": [self.raw_code], "exchange_code": [self.exchange_code], "convert_premium_rate": [10.0]})
        mock_jq.bond.run_query.side_effect = [self._mock_bonds_info(), premium]
        mock_jq.get_extras.return_value = pd.DataFrame({self.underlying: [True]}, index=pd.to_datetime(["2024-01-03"]))

        mock_validator.return_value.validate_dataframe.return_value = False
        mock_semantic_validator.return_value.validate_dataframe.return_value = True

        with patch("sys.stdout", new_callable=unittest.mock.MagicMock), patch("os.replace") as mock_replace:
            with self.assertRaises(SystemExit) as cm:
                sync_cb_data("2024-01-03", "2024-01-03")

            self.assertNotEqual(cm.exception.code, 0)
            calls = [call for call in mock_replace.mock_calls if "cb_history_factors.csv.tmp" in str(call)]
            self.assertEqual(len(calls), 0)

    @patch("etl.jqdata_sync_cb.jqdatasdk")
    @patch("ams.validators.cb_data_validator.DatasetSemanticValidator")
    @patch("ams.validators.cb_data_validator.CBDataValidator")
    def test_etl_atomic_rollback_on_promotion_error(self, mock_validator, mock_semantic_validator, mock_jq):
        os.environ["JQDATA_USER"] = "test"
        os.environ["JQDATA_PWD"] = "test"
        mock_jq.auth.return_value = None
        mock_jq.get_all_securities.return_value = pd.DataFrame(index=[self.ticker])
        mock_jq.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True
        mock_jq.get_price.return_value = self._single_price_df("2024-01-03")
        premium = pd.DataFrame({"date": ["2024-01-03"], "code": [self.raw_code], "exchange_code": [self.exchange_code], "convert_premium_rate": [10.0]})
        mock_jq.bond.run_query.side_effect = [self._mock_bonds_info(), premium]
        mock_jq.get_extras.return_value = pd.DataFrame({self.underlying: [True]}, index=pd.to_datetime(["2024-01-03"]))

        mock_validator.return_value.validate_dataframe.return_value = True
        mock_semantic_validator.return_value.validate_dataframe.return_value = True

        original_replace = os.replace

        def mock_replace(src, dst):
            if src == f"{resolve_provider_dataset_path("jqdata")}.tmp":
                raise OSError("Mock failure")
            return original_replace(src, dst)

        with patch("os.replace", side_effect=mock_replace):
            with self.assertRaises(SystemExit) as cm:
                sync_cb_data("2024-01-03", "2024-01-03")

            self.assertNotEqual(cm.exception.code, 0)

    @patch("etl.jqdata_sync_cb.jqdatasdk")
    @patch("ams.validators.cb_data_validator.DatasetSemanticValidator")
    @patch("ams.validators.cb_data_validator.CBDataValidator")
    def test_promotion_validation_prints_error_messages(self, mock_validator, mock_semantic_validator, mock_jq):
        os.environ["JQDATA_USER"] = "test"
        os.environ["JQDATA_PWD"] = "test"
        mock_jq.auth.return_value = None
        mock_jq.get_all_securities.return_value = pd.DataFrame(index=[self.ticker])
        mock_jq.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True
        mock_jq.get_price.return_value = self._single_price_df("2024-01-03")
        premium = pd.DataFrame({"date": ["2024-01-03"], "code": [self.raw_code], "exchange_code": [self.exchange_code], "convert_premium_rate": [10.0]})
        mock_jq.bond.run_query.side_effect = [self._mock_bonds_info(), premium]
        mock_jq.get_extras.return_value = pd.DataFrame({self.underlying: [True]}, index=pd.to_datetime(["2024-01-03"]))

        mock_validator.return_value.validate_dataframe.return_value = False
        mock_validator.return_value.last_error_message = "[DataContractViolation] close must be positive"
        mock_semantic_validator.return_value.validate_dataframe.side_effect = AssertionError(
            "legacy DatasetSemanticValidator must not run in Stage F"
        )

        from io import StringIO
        import sys

        captured_output = StringIO()
        original_stdout = sys.stdout
        try:
            sys.stdout = captured_output
            with self.assertRaises(SystemExit) as cm:
                sync_cb_data("2024-01-03", "2024-01-03")
            self.assertNotEqual(cm.exception.code, 0)
        finally:
            sys.stdout = original_stdout

        output = captured_output.getvalue()
        self.assertIn("[DataContractViolation] close must be positive", output)
        mock_semantic_validator.return_value.validate_dataframe.assert_not_called()

    @patch("etl.jqdata_sync_cb.jqdatasdk")
    @patch("ams.validators.cb_data_validator.DatasetSemanticValidator")
    @patch("ams.validators.cb_data_validator.CBDataValidator")
    def test_rollback_preserves_canonical_data_if_backup_fails(self, mock_validator, mock_semantic_validator, mock_jq):
        os.environ["JQDATA_USER"] = "test"
        os.environ["JQDATA_PWD"] = "test"
        mock_jq.auth.return_value = None
        mock_jq.get_all_securities.return_value = pd.DataFrame(index=[self.ticker])
        mock_jq.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True
        mock_jq.get_price.return_value = self._single_price_df("2024-01-03")
        premium = pd.DataFrame({"date": ["2024-01-03"], "code": [self.raw_code], "exchange_code": [self.exchange_code], "convert_premium_rate": [10.0]})
        mock_jq.bond.run_query.side_effect = [self._mock_bonds_info(), premium]
        mock_jq.get_extras.return_value = pd.DataFrame({self.underlying: [True]}, index=pd.to_datetime(["2024-01-03"]))

        mock_validator.return_value.validate_dataframe.return_value = True
        mock_semantic_validator.return_value.validate_dataframe.return_value = True

        mock_data_path = "/tmp/mock_cb_data.csv"
        mock_metrics_path = "/tmp/mock_metrics.json"

        original_replace = os.replace

        def mock_replace(src, dst):
            if src == mock_data_path and dst == mock_data_path + ".bak":
                raise OSError("Mock failure: Cannot backup canonical file")
            return original_replace(src, dst)

        with open(mock_data_path, "w") as f:
            f.write("dummy")

        try:
            with patch.dict("os.environ", {"AMS_JQDATA_DATASET_PATH": mock_data_path, "AMS_JQDATA_METRICS_PATH": mock_metrics_path}), patch("os.replace", side_effect=mock_replace), patch("os.remove") as mock_remove:
                with self.assertRaises(SystemExit) as cm:
                    sync_cb_data("2024-01-03", "2024-01-03")

                self.assertNotEqual(cm.exception.code, 0)
                calls = [call for call in mock_remove.mock_calls if mock_data_path in str(call)]
                self.assertEqual(len(calls), 0)
        finally:
            if os.path.exists(mock_data_path):
                os.remove(mock_data_path)
            if os.path.exists(mock_metrics_path):
                os.remove(mock_metrics_path)

    @patch("etl.jqdata_provider.jqdatasdk")
    def test_premium_batched_fetch_combines_multiple_months(self, mock_jq):
        # Setup: Mock JQData run_query to return different sets of data for two different months.
        pipeline = CBETLPipeline("2024-01-01", "2024-02-15", jqdata_provider=mock_jq)
        
        mock_jq.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True

        # Month 1: 2024-01
        df_m1 = pd.DataFrame({
            "date": ["2024-01-15"],
            "code": ["123456.XSHG"],
            "convert_premium_rate": [10.0]
        })
        # Month 2: 2024-02
        df_m2 = pd.DataFrame({
            "date": ["2024-02-15"],
            "code": ["123456.XSHG"],
            "convert_premium_rate": [20.0]
        })
        
        mock_jq.bond.run_query.side_effect = [df_m1, df_m2]

        # Execution: Call _fetch_premium_batched
        res = pipeline._fetch_premium_batched(["123456"], "2024-01-01", "2024-02-15")

        # Assertion:
        self.assertEqual(len(res), 2)
        self.assertEqual(mock_jq.bond.run_query.call_count, 2)

    @patch("etl.jqdata_provider.jqdatasdk")
    def test_premium_truncation_guard_logs_message(self, mock_jq):
        # Setup: Mock JQData run_query to return exactly 5000 rows for one of the batches.
        pipeline = CBETLPipeline("2024-01-01", "2024-01-31", jqdata_provider=mock_jq)
        
        mock_jq.bond.CONBOND_DAILY_CONVERT.code.in_.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__ge__.return_value = True
        mock_jq.bond.CONBOND_DAILY_CONVERT.date.__le__.return_value = True

        # Return 5000 rows
        df_5000 = pd.DataFrame([{"date": "2024-01-01", "code": "123456.XSHG", "convert_premium_rate": 10.0}] * 5000)
        mock_jq.bond.run_query.return_value = df_5000

        # Execution & Assertion:
        with self.assertRaises(RuntimeError) as cm:
            pipeline._fetch_premium_batched(["123456"], "2024-01-01", "2024-01-31")

        self.assertEqual(str(cm.exception), "Premium source query returned the provider single-call cap characteristic and must be retried with deterministic batching.")

    def test_validator_skips_on_missing_columns(self):

        # Setup: Create a CBETLPipeline instance.
        pipeline = CBETLPipeline("2024-01-01", "2024-01-01")
        from etl.cb_etl_pipeline import CANONICAL_CB_COLUMNS
        cols = [c for c in CANONICAL_CB_COLUMNS if c != "is_st"]
        df = pd.DataFrame(columns=cols + ["supportability_bucket"])
        # Use dummy values that match the length
        dummy_row = []
        for c in cols:
            if c in ["open", "high", "low", "close", "volume", "premium_rate", "double_low"]:
                dummy_row.append(0.0)
            elif c in ["is_st", "is_redeemed"]:
                dummy_row.append(False)
            else:
                dummy_row.append("dummy")
        
        df.loc[0] = dummy_row + [SUPPORTABILITY_BUCKET_SUPPORTABLE]
        pipeline.df = df

        # Execution: Call run_stage_f_validator().
        res = pipeline.run_stage_f_validator()

        # Assertion:
        self.assertFalse(res)
        self.assertEqual(pipeline.results["validator_summary"]["status"], "FAIL")
        self.assertEqual(pipeline.results["validator_summary"]["failure_type"], "VALIDATOR_SCHEMA_FAILURE")
        self.assertIn("Validator skipped because required canonical columns are missing after upstream stage failures:",
                      pipeline.results["validator_summary"]["message"])
        self.assertIn("is_st", pipeline.results["validator_summary"]["message"])

    def test_validator_passes_when_columns_present(self):
        # Setup: Provide a DataFrame with all CANONICAL_CB_COLUMNS and valid data.
        pipeline = CBETLPipeline("2024-01-01", "2024-01-01")
        from etl.cb_etl_pipeline import CANONICAL_CB_COLUMNS
        df = pd.DataFrame(columns=CANONICAL_CB_COLUMNS + ["supportability_bucket"])
        # Mock some valid data
        data = {
            "ticker": "123456.XSHG",
            "date": "2024-01-01",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1000,
            "premium_rate": 0.1,
            "double_low": 110.0,
            "underlying_ticker": "600000.XSHG",
            "is_st": False,
            "is_redeemed": False,
            "supportability_bucket": SUPPORTABILITY_BUCKET_SUPPORTABLE
        }
        df.loc[0] = [data[c] for c in CANONICAL_CB_COLUMNS] + [data["supportability_bucket"]]
        pipeline.df = df

        # Mock validators to avoid business logic failure
        with patch("ams.validators.cb_data_validator.CBDataValidator") as mock_v1, \
             patch("ams.validators.cb_data_validator.DatasetSemanticValidator") as mock_v2:
            mock_v1.return_value.validate_dataframe.return_value = True
            mock_v2.return_value.validate_dataframe.return_value = True

            # Execution: Call run_stage_f_validator().
            res = pipeline.run_stage_f_validator()

            # Assertion:
            self.assertTrue(res)
            self.assertEqual(pipeline.results["validator_summary"]["status"], "PASS")

    @patch("etl.jqdata_provider.jqdatasdk")
    def test_is_st_handles_provider_window_exception(self, mock_jq):
        # Setup
        pipeline = CBETLPipeline(self.start_date, self.end_date, jqdata_provider=mock_jq)
        pipeline.results["source_coverage"]["status"] = "PASS"
        
        # Mock supportable bonds
        df = pd.DataFrame({
            "bond_code_raw": ["123456"],
            "bond_exchange_code": ["XSHG"],
            "date": [pd.to_datetime(self.start_date)],
            "supportability_bucket": [SUPPORTABILITY_BUCKET_SUPPORTABLE],
            "underlying_ticker": [self.underlying]
        })
        pipeline.df = df
        
        # Mock get_extras to raise window exception
        exception_msg = "Date window exceeds account permissions"
        mock_jq.get_extras.side_effect = Exception(exception_msg)
        
        # Execution
        res = pipeline.run_stage_d_is_st_join()
        
        # Assertion
        summary = pipeline.results["is_st_join_summary"]
        self.assertFalse(res)
        self.assertEqual(summary["status"], "FAIL")
        self.assertEqual(summary["failure_type"], "IS_ST_SOURCE_GAP")
        self.assertIn("is_st source query exceeded the provider-supported date window", summary["message"])
        self.assertIn(exception_msg, summary["message"])

    @patch("etl.jqdata_provider.jqdatasdk")
    def test_is_st_detects_empty_source_as_gap(self, mock_jq):
        # Setup
        pipeline = CBETLPipeline(self.start_date, self.end_date, jqdata_provider=mock_jq)
        pipeline.results["source_coverage"]["status"] = "PASS"
        
        # Mock supportable bonds
        df = pd.DataFrame({
            "bond_code_raw": ["123456"],
            "bond_exchange_code": ["XSHG"],
            "date": [pd.to_datetime(self.start_date)],
            "supportability_bucket": [SUPPORTABILITY_BUCKET_SUPPORTABLE],
            "underlying_ticker": [self.underlying]
        })
        pipeline.df = df
        
        # Mock get_extras to return empty DataFrame
        mock_jq.get_extras.return_value = pd.DataFrame()
        
        # Execution
        res = pipeline.run_stage_d_is_st_join()
        
        # Assertion
        summary = pipeline.results["is_st_join_summary"]
        self.assertFalse(res)
        self.assertEqual(summary["status"], "FAIL")
        self.assertEqual(summary["failure_type"], "IS_ST_SOURCE_GAP")
        self.assertEqual(summary["missing_is_st_ratio"], 1.0)

if __name__ == "__main__":
    unittest.main()
