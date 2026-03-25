#!/usr/bin/env python3
"""
腾讯 ETF 套利监控 - 定时任务入口
检测到套利机会时发送消息提醒
"""

import subprocess
import sys
import json
from pathlib import Path
from datetime import datetime

# 路径配置
SCRIPT_DIR = Path(__file__).parent
MONITOR_SCRIPT = SCRIPT_DIR / "monitor.py"
ALERT_FILE = SCRIPT_DIR / "latest_alert.txt"
PID_FILE = SCRIPT_DIR / ".monitor.pid"

def is_trading_time():
    """检查是否在交易时段"""
    now = datetime.now()
    hour = now.hour
    minute = now.minute
    weekday = now.weekday()  # 0=周一, 6=周日
    
    # 周末不交易
    if weekday >= 5:
        return False
    
    # 交易时段: 9:30-11:30, 13:00-15:00
    time_val = hour * 100 + minute
    return (930 <= time_val <= 1130) or (1300 <= time_val <= 1500)

def main():
    # 检查是否在交易时段
    if not is_trading_time():
        print(f"非交易时段: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        return
    
    # 检查是否已有实例在运行 (防止重叠)
    if PID_FILE.exists():
        try:
            with open(PID_FILE, 'r') as f:
                data = json.load(f)
                last_time = datetime.fromisoformat(data['time'])
                seconds_ago = (datetime.now() - last_time).total_seconds()
                if seconds_ago < 300:  # 5分钟内
                    print(f"上次运行在 {seconds_ago:.0f}秒前，跳过")
                    return
        except:
            pass
    
    # 记录运行时间
    with open(PID_FILE, 'w') as f:
        json.dump({'time': datetime.now().isoformat()}, f)
    
    # 运行监控脚本
    result = subprocess.run(
        [sys.executable, str(MONITOR_SCRIPT)],
        capture_output=True,
        text=True,
        timeout=30
    )
    
    # 打印输出
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    
    # 如果有提醒消息，输出特定格式供OpenClaw捕获
    if ALERT_FILE.exists():
        try:
            with open(ALERT_FILE, 'r') as f:
                alert_msg = f.read().strip()
            if alert_msg:
                # 输出特殊标记，供OpenClaw识别并推送
                print("\n" + "="*50)
                print("ARB_ALERT_START")
                print(alert_msg)
                print("ARB_ALERT_END")
                print("="*50)
        except:
            pass

if __name__ == "__main__":
    main()
