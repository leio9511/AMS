import akshare as ak
try:
    df = ak.stock_financial_cash_ths(symbol="600519")
    print("Found columns:", df.columns[:5])
    print(df.head(1))
except Exception as e:
    print("Error:", e)
