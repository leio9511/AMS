import akshare as ak
import time
import socket
socket.setdefaulttimeout(10)

def run_spike():
    print("=== AKShare API Spike for 6-Layer Filtering Funnel ===\n")

    SYMBOL = "600519"
    print(f"Testing with symbol: {SYMBOL}\n")

    # Layer 1: Macro Gate (Industry Classification)
    print("1. Industry Classification (Macro Gate)")
    print("Function: ak.stock_individual_info_em")
    try:
        info = ak.stock_individual_info_em(symbol=SYMBOL)
        industry = info[info['item'] == '行业']['value'].values[0]
        print(f"Result for {SYMBOL}: {industry}")
        print("-> Maps to: Industry classification requirement.\n")
    except Exception as e:
        print(f"Failed: {e}\n")

    # Layer 2: Yield Base (YTD Return & PE/PB)
    print("2. Yield Base (YTD Return & PE/PB History)")
    print("Function: ak.stock_zh_a_hist (Used to calculate YTD and historical percentiles)")
    try:
        hist = ak.stock_zh_a_hist(symbol=SYMBOL, period="daily", start_date="20240101", end_date="20241231")
        print(f"Fetched historical data rows: {len(hist)}.")
        print("Columns available for PE/PB/YTD calcs:", hist.columns.tolist()[:6])
        print(f"Sample price data:\n{hist[['日期', '开盘', '收盘', '涨跌幅']].head(1)}")
        print("-> Maps to: YTD Return and historical PE/PB percentile calculations.\n")
    except Exception as e:
        print(f"Failed: {e}\n")

    # Layer 3: Safety Margin (Forward PE & Profit Growth)
    print("3. Safety Margin (Forward PE, Net Profit Growth Forecast)")
    print("Function: ak.stock_profit_forecast_ths")
    try:
        # NOTE: This API frequently times out in CI.
        # Uncomment in local environments:
        # forecast = ak.stock_profit_forecast_ths(symbol=SYMBOL)
        print("Columns: ['年度', '预测机构数', '最小值', '均值', '最大值', '行业平均数']")
        print("Sample EPS forecast (Mocked due to CI timeout):")
        print("     年度  预测机构数    最小值    均值    最大值  行业平均数")
        print("0  2025     46  71.54  72.6  75.23   9.64")
        print("-> Maps to: Forward PE (Price / EPS forecast) and Net Profit Growth Forecast.\n")
    except Exception as e:
        print(f"Failed: {e}\n")

    # Layer 4 & 5: Balance Sheet & Cash Flow (Current Ratio, Debt-to-Asset, Operating Cash Flow)
    print("4 & 5. Balance Sheet & Cash Flow Metrics")
    print("Functions: ak.stock_financial_abstract_ths & ak.stock_financial_cash_ths")
    try:
        bs = ak.stock_financial_abstract_ths(symbol=SYMBOL)
        print(f"Sample metrics (Asset/Liability, etc):\n{bs[['报告期', '资产负债率', '速动比率']].head(1)}")
        print("-> Maps to: Current Ratio, Debt-to-Asset Ratio.\n")
        
        cf = ak.stock_financial_cash_ths(symbol=SYMBOL)
        print(f"Sample Net Operating Cash Flow:\n{cf[['报告期', '*经营活动产生的现金流量净额']].head(1)}")
        print("-> Maps to: Operating Cash Flow.\n")
    except Exception as e:
        print(f"Failed: {e}\n")

    print("=== Spike Complete ===")

if __name__ == "__main__":
    run_spike()
