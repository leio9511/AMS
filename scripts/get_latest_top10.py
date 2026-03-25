import json
import os

result_path = "AMS/reports/stock_radar_result.json"
if os.path.exists(result_path):
    with open(result_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        top_10 = data.get('top_results', [])[:10]
        print(f"📊 选股结果快照 (Run time: {data.get('run_time')})")
        print("-" * 40)
        print(f"{'No.':<4} {'Name':<12} {'Code':<8} {'PE':<6} {'Score'}")
        for i, s in enumerate(top_10):
            print(f"{i+1:<4} {s['name']:<12} {s['code']:<8} {s['pe']:<6.1f} {s['score']:.1f}")
else:
    print("未发现最新的选股结果文件。")
