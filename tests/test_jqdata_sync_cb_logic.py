import json
import os
import unittest
from unittest.mock import patch

import pandas as pd

from etl.jqdata_sync_cb import sync_cb_data


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
                "code": [self.ticker],
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

        df = pd.read_csv("/root/projects/AMS/data/cb_history_factors.csv")
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

        df = pd.read_csv("/root/projects/AMS/data/cb_history_factors.csv")
        self.assertEqual(df["underlying_ticker"].iloc[0], self.underlying)
        self.assertTrue(df["is_st"].iloc[0])

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

        bonds_info = pd.DataFrame({"code": ["123071.XSHE"], "company_code": ["000001.XSHE"], "delist_Date": ["2024-12-31"]})
        premium = pd.DataFrame({"date": ["2024-01-03"], "code": ["123071"], "exchange_code": ["XSHE"], "convert_premium_rate": [15.5]})
        mock_jq.bond.run_query.side_effect = [bonds_info, premium]
        mock_jq.get_extras.return_value = pd.DataFrame({"000001.XSHE": [False]}, index=pd.to_datetime(["2024-01-03"]))
        mock_validator.return_value.validate_dataframe.return_value = True

        sync_cb_data("2024-01-03", "2024-01-03")

        df = pd.read_csv("/root/projects/AMS/data/cb_history_factors.csv")
        self.assertEqual(df["premium_rate"].iloc[0], 0.155)
        with open("/root/projects/AMS/data/cb_history_factors.metrics.json", "r", encoding="utf-8") as f:
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

        df = pd.read_csv("/root/projects/AMS/data/cb_history_factors.csv")
        self.assertTrue(df["is_redeemed"].iloc[0])
        with open("/root/projects/AMS/data/cb_history_factors.metrics.json", "r", encoding="utf-8") as f:
            metrics = json.load(f)
        self.assertEqual(metrics["is_redeemed_missing_delist_count"], 0)

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

        df = pd.read_csv("/root/projects/AMS/data/cb_history_factors.csv")
        self.assertTrue(df["is_st"].iloc[0])




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
            
            # Assert os.replace was called for tmp to canonical
            calls = [call for call in mock_replace.mock_calls if 'data/cb_history_factors.csv.tmp' in str(call)]
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
        
        mock_validator.return_value.validate_dataframe.return_value = True
        mock_semantic_validator.return_value.validate_dataframe.return_value = False  # Validation fails

        with patch("sys.stdout", new_callable=unittest.mock.MagicMock) as mock_stdout, patch("os.replace") as mock_replace:
            with self.assertRaises(SystemExit) as cm:
                sync_cb_data("2024-01-03", "2024-01-03")
            
            self.assertNotEqual(cm.exception.code, 0)
            
            # Canonical paths should not be overwritten
            calls = [call for call in mock_replace.mock_calls if 'data/cb_history_factors.csv.tmp' in str(call)]
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
            if src == "/root/projects/AMS/data/cb_history_factors.csv.tmp":
                raise OSError("Mock failure")
            return original_replace(src, dst)

        with patch("os.replace", side_effect=mock_replace):
            with self.assertRaises(SystemExit) as cm:
                sync_cb_data("2024-01-03", "2024-01-03")
            
            self.assertNotEqual(cm.exception.code, 0)

if __name__ == "__main__":
    unittest.main()
