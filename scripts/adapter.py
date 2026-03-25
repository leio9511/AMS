import pandas as pd
import akshare as ak
import os
import time

def qmt_to_akshare(qmt_data):
    """
    Maps QMT get_full_tick response to AkShare stock_zh_a_spot_em format.
    """
    rows = []
    for code, tick in qmt_data.items():
        short_code = code.split('.')[0]
        
        last_price = tick.get('lastPrice', 0)
        last_close = tick.get('lastClose', 0)
        
        change = last_price - last_close if last_close else 0
        change_pct = (change / last_close * 100) if last_close else 0
        
        row = {
            '代码': short_code,
            '名称': tick.get('stockName', ''),
            '最新价': last_price,
            '涨跌幅': change_pct,
            '涨跌额': change,
            '成交量': tick.get('volume', 0),
            '成交额': tick.get('amount', 0),
            '最高': tick.get('high', 0),
            '最低': tick.get('low', 0),
            '今开': tick.get('open', 0),
            '昨收': last_close,
        }
        rows.append(row)
    
    return pd.DataFrame(rows)

