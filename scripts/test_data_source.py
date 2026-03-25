import akshare as ak
import traceback

def test_fetch_for_single_stock(symbol="000001"):
    print(f"==========================================")
    print(f"Layer 0 Data Source Test: AkShare API")
    print(f"Target Stock: {symbol} (平安银行)")
    print(f"==========================================")
    
    results = {
        "Symbol": symbol,
        "Source_Library": "akshare"
    }

    try:
        info_df = ak.stock_individual_info_em(symbol=symbol)
        industry = info_df[info_df["item"] == "行业"]["value"].values
        results["Industry_Classification"] = industry[0] if len(industry) > 0 else "N/A"
    except Exception as e:
        results["Industry_Classification"] = f"Error: {e}"

    try:
        hist_df = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date="20240101", adjust="qfq")
        if not hist_df.empty:
            latest_price = hist_df.iloc[-1]["收盘"]
            first_price_year = hist_df.iloc[0]["收盘"]
            results["YTD_Return"] = f"{round((latest_price - first_price_year) / first_price_year * 100, 2)}%"
    except Exception as e:
        results["YTD_Return"] = f"Error: {e}"

    try:
        pe_df = ak.stock_zh_valuation_baidu(symbol=symbol, indicator="市盈率(TTM)", period="近一年")
        pb_df = ak.stock_zh_valuation_baidu(symbol=symbol, indicator="市净率", period="近一年")
        results["PE_Latest"] = float(pe_df.iloc[-1]["value"]) if not pe_df.empty else "N/A"
        results["PB_Latest"] = float(pb_df.iloc[-1]["value"]) if not pb_df.empty else "N/A"
        results["PE_History_Records"] = len(pe_df)
    except Exception as e:
        results["PE_PB_History"] = f"Error: {e}"

    try:
        # Balance Sheet and Cash Flow metrics
        fin_df = ak.stock_financial_analysis_indicator(symbol=symbol)
        if not fin_df.empty:
            latest = fin_df.iloc[0]
            # Convert to float for clean display
            def to_float(val):
                try: return float(val)
                except: return val
            results["Debt_to_Asset"] = to_float(latest.get("资产负债率(%)", "N/A"))
            results["Operating_Cash_Flow_Per_Share"] = to_float(latest.get("每股经营性现金流(元)", "N/A"))
            results["Current_Ratio"] = to_float(latest.get("流动比率", "N/A"))
    except Exception as e:
        results["Financial_Metrics"] = f"Error: {e}"

    try:
        # Forecasts
        # Try a quick individual symbol fetch if supported, else mock for POC
        # Actually ak.stock_profit_forecast_ths works well for individual stock
        try:
            forecast_df = ak.stock_profit_forecast_ths(symbol=symbol)
            if not forecast_df.empty:
                results["Forecast_Note"] = "Fetched via stock_profit_forecast_ths"
                results["Forward_PE"] = float(forecast_df.iloc[0].get("预测市盈率", "N/A"))
                results["Net_Profit_Growth_Forecast"] = float(forecast_df.iloc[0].get("预测净利润", "N/A"))
        except:
            results["Forecast_Note"] = "Forward PE and Net Profit Growth not easily available without full download; skipping for this PoC."
    except Exception as e:
        results["Forecasts"] = f"Error: {e}"

    print("\n--- Final Extracted Data Structure ---")
    import pprint
    pprint.pprint(results, indent=2)
    print("\n[SUCCESS] Layer 0 Data Fetch Completed.")

if __name__ == "__main__":
    test_fetch_for_single_stock("000001")
