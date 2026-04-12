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
            
        # Transform dict of dicts to list of dicts, injecting the stock code
        records = []
        if isinstance(raw_data, dict):
            for code, data in raw_data.items():
                if code.endswith('.HK'):
                    continue
                record = data.copy()
                # Use raw '代码' format from key
                record["stock_code"] = code.split('.')[0] if '.' in code else code
                # Support both 'stock_name' and 'stockName'
                if "stockName" in record and "stock_name" not in record:
                    record["stock_name"] = record["stockName"]
                if "lastClose" in record and "preClose" not in record:
                    record["preClose"] = record["lastClose"]
                records.append(record)
        else:
            records = raw_data
            
        df = pd.DataFrame(records)
        
        # Rename columns according to mapping
        rename_dict = {k: v for k, v in FIELD_MAPPING.items() if k in df.columns}
        df = df.rename(columns=rename_dict)
        
        # Ensure all expected columns exist
        for col in FIELD_MAPPING.values():
            if col not in df.columns:
                df[col] = None
                
        return df

    def get_stock_hk_spot_em(self) -> pd.DataFrame:
        raw_data = self.qmt_client.get_full_tick()
        
        if not raw_data:
            return pd.DataFrame(columns=list(FIELD_MAPPING.values()))
            
        records = []
        if isinstance(raw_data, dict):
            for code, data in raw_data.items():
                if not code.endswith('.HK'):
                    continue
                record = data.copy()
                record["stock_code"] = code.split('.')[0] if '.' in code else code
                if "stockName" in record and "stock_name" not in record:
                    record["stock_name"] = record["stockName"]
                if "lastClose" in record and "preClose" not in record:
                    record["preClose"] = record["lastClose"]
                records.append(record)
        else:
            records = raw_data
            
        df = pd.DataFrame(records)
        
        rename_dict = {k: v for k, v in FIELD_MAPPING.items() if k in df.columns}
        df = df.rename(columns=rename_dict)
        
        for col in FIELD_MAPPING.values():
            if col not in df.columns:
                df[col] = None
                
        return df
