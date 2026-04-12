import sys
import pandas as pd
sys.path.append("/root/.openclaw/workspace/projects/AMS")
from scripts.qmt_client import QMTClient
from scripts.qmt_data_adapter import QMTDataAdapter

def main():
    print("🚀 初始化 QMT 客户端...")
    client = QMTClient()
    adapter = QMTDataAdapter(client)
    
    print("📡 正在尝试通过 QMTClient 获取指定股票（平安银行与腾讯）的 Tick 数据...")
    # 这里我们只取少量代码验证格式是否完美匹配，避免全量拉取刷屏
    client.get_full_tick = lambda: QMTClient().get_full_tick(["000001.SZ", "00700.HK"])
    
    df_a = adapter.get_stock_zh_a_spot_em()
    print(f"\n✅ 成功解析 A 股数据 ({len(df_a)} 只):")
    if not df_a.empty:
        print(df_a.to_markdown())
        
    df_hk = adapter.get_stock_hk_spot_em()
    print(f"\n✅ 成功解析 港股数据 ({len(df_hk)} 只):")
    if not df_hk.empty:
        print(df_hk.to_markdown())

if __name__ == "__main__":
    main()
