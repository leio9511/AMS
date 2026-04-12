import sys
sys.path.append("/root/.openclaw/workspace/projects/AMS")
from scripts.qmt_client import QMTClient
from scripts.qmt_data_adapter import QMTDataAdapter

def main():
    try:
        client = QMTClient()
        print(f"Connecting to QMT Server at {client.base_url}...")
        
        adapter = QMTDataAdapter(client)
        df = adapter.get_stock_zh_a_spot_em()
        
        print("\n--- 成功从 Windows QMT 节点拉取数据 ---")
        print(f"共获取到 {len(df)} 只标的")
        if len(df) > 0:
            print("\nDataFrame 前 5 行示例:")
            print(df.head().to_markdown())
            print("\n涵盖的列名:", df.columns.tolist())
            
    except Exception as e:
        print(f"验证失败: {e}")

if __name__ == "__main__":
    main()
