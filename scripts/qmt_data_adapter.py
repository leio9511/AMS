import pandas as pd
from scripts.qmt_client import QMTClient

FIELD_MAPPING = {
    "stock_code": "代码",
    "stock_name": "名称",
    "lastPrice": "最新价",
    "open": "今开",
    "high": "最高",
    "low": "最低",
    "preClose": "昨收",
    "volume": "成交量",
    "amount": "成交额",
    "changePercent": "涨跌幅"
}

class QMTDataAdapter:
    def __init__(self, qmt_client: QMTClient):
        self.qmt_client = qmt_client

    def get_stock_zh_a_spot_em(self) -> pd.DataFrame:
        raw_data = self.qmt_client.get_full_tick()
        
        if not raw_data:
            return pd.DataFrame(columns=list(FIELD_MAPPING.values()))
            
        df = pd.DataFrame(raw_data)
        
        # Rename columns according to mapping
        rename_dict = {k: v for k, v in FIELD_MAPPING.items() if k in df.columns}
        df = df.rename(columns=rename_dict)
        
        # Ensure all expected columns exist
        for col in FIELD_MAPPING.values():
            if col not in df.columns:
                df[col] = None
                
        return df
