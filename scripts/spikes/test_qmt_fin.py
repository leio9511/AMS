import sys
sys.path.append("/root/.openclaw/workspace/projects/AMS")
import httpx
import json

def main():
    print("🚀 测试通过 QMTClient 调用 get_financial_data...")
    url = "http://43.134.76.215:8000/api/xtdata_call"
    payload = {
        "method": "get_financial_data",
        "args": [["000001.SZ"]],
        "kwargs": {"table_list": ["Capital", "Balance", "Income", "CashFlow"]}
    }
    
    resp = httpx.post(url, json=payload, timeout=30)
    print("Response Status:", resp.status_code)
    try:
        data = resp.json()
        print("Data keys:", data.keys())
        if data.get("status") == "success":
            result = data.get("data", {})
            for stock, tables in result.items():
                print(f"--- {stock} ---")
                for table, df_dict in tables.items():
                    print(f"  Table: {table}")
                    if df_dict:
                        # dict is like {"index": [...], "columns": [...], "data": [...]} if it's pandas converted
                        print(f"  Snippet: {str(df_dict)[:500]}...")
                    else:
                        print("  Empty")
        else:
            print("Server returned error:", data)
    except Exception as e:
        print("Failed to parse response:", e)

if __name__ == "__main__":
    main()
