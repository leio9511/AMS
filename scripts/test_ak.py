import akshare as ak
try:
    df = ak.stock_a_indicator_lg(symbol="all")
    print(df.columns.tolist())
    print(df.head(2))
except Exception as e:
    print(e)
