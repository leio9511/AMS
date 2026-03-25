#!/usr/bin/env python3
"""
套利监控定时任务入口
由cron调用，检测到机会时发送消息提醒
"""

import subprocess
import sys
from pathlib import Path

# 获取监控脚本路径
SCRIPT_DIR = Path(__file__).parent
MONITOR_SCRIPT = SCRIPT_DIR / "monitor.py"

def main():
    # 运行监控脚本
    result = subprocess.run(
        [sys.executable, str(MONITOR_SCRIPT)],
        capture_output=True,
        text=True
    )
    
    # 打印输出
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    
    # 如果有提醒消息，输出到stdout (会被cron捕获)
    # 消息已在monitor.py中输出

if __name__ == "__main__":
    main()
