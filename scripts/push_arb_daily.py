import subprocess
import os
from datetime import datetime

def send_telegram(msg):
    # 直接调用 message 接口，这是最可靠的方式
    # 这里通过 exec 调用 python 脚本发送
    subprocess.run(["openclaw", "message", "send", "--target", "agent:main:main", "--channel", "telegram", "--message", msg])

try:
    # 1. 运行监控脚本并获取输出字符串
    res1 = subprocess.check_output(["python3", "strategies/cross_border_etf_monitor.py"], text=True)
    res2 = subprocess.check_output(["python3", "strategies/tencent_etf_arb/monitor.py"], text=True)

    content = res1 + "\n" + res2
    
    header = f"📊 AMS 实时套利监控报告 ({datetime.now().strftime('%H:%M')})\n"
    
    # 2. 发送汇总报告
    if len(content.strip()) > 100: # 确保不是空内容
        if len(content) > 3500:
            content = content[:3500] + "\n...(数据过长已截断)"
        send_telegram(header + content)
        print("Telegram push successful.")
    else:
        print("No active signals to push.")

except Exception as e:
    print(f"Error during push: {e}")
