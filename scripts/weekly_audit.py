import json
import os
import subprocess
from datetime import datetime

TARGET = "telegram:6228532305"

def send_telegram(msg):
    """发送消息到 Telegram"""
    try:
        result = subprocess.run(
            ["openclaw", "message", "send", "--channel", "telegram", "--target", TARGET, "--message", msg],
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode == 0
    except Exception as e:
        print(f"[ERROR] 发送消息失败: {e}")
        return False

def run_weekly_scan():
    """运行周六选股雷达 - 水晶苍蝇拍 26.3"""
    print(f"[*] Starting weekly stock radar scan at {datetime.now()}")
    
    try:
        result = subprocess.run(
            ["python3", "AMS/scripts/pilot_stock_radar.py"],
            capture_output=True,
            text=True,
            timeout=600  # 10分钟超时
        )
        
        if result.returncode != 0:
            print(f"[ERROR] 选股雷达运行失败: {result.stderr}")
            send_telegram(f"❌ 【水晶苍蝇拍 26.3】运行失败\n错误: {result.stderr[:200]}")
            return
        
        # 读取结果
        result_path = "AMS/reports/stock_radar_sector.json"
        if not os.path.exists(result_path):
            print("[ERROR] 结果文件不存在")
            send_telegram("❌ 【水晶苍蝇拍 26.3】结果文件不存在")
            return
        
        with open(result_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 生成报告
        final_picks = data.get('final_picks', [])[:20]  # Top 20
        perf = data.get('performance', {})
        
        report_lines = [
            "🪰 【水晶苍蝇拍 26.3】",
            f"📅 周报 ({datetime.now().strftime('%Y-%m-%d')})",
            "━" * 25,
            f"📊 扫描: {perf.get('total_scanned', 0)} 只",
            f"✅ 入选: {perf.get('final_passed', 0)} 只",
            f"⏱️ 耗时: {perf.get('total_time_seconds', 0):.1f}秒",
            "━" * 25,
            "",
            "📋 策略标准:",
            "1️⃣ 今年大跌",
            "2️⃣ 深度熊市估值(PE≤8加分)",
            "3️⃣ 业绩增长好",
            "4️⃣ 资产质量顶尖",
            "5️⃣ 受益通胀/无关石油",
            "→ 至少符合4条 + 必须项",
            "→ 2026PE ≤ 20 (低PE优先)",
            "",
            "━" * 25,
            ""
        ]
        
        # Top 20
        report_lines.append("🏆 【优选标的】")
        for i, s in enumerate(final_picks, 1):
            market = s.get('market', '?')
            name = s.get('name', '?')
            code = s.get('code', '?')
            score = s.get('score', 0)
            pe = s.get('pe_forecast', 0)
            advantage = s.get('advantage', '')
            met = s.get('met_count', 0)
            
            report_lines.append(f"{i:2d}. [{market}] {name}({code})")
            report_lines.append(f"    分数:{score:.0f} PE:{pe:.1f} 符合:{met}条")
            report_lines.append(f"    {advantage}")
        
        report_lines.extend([
            "",
            "━" * 25,
            "💡 详细数据见 AMS/reports/"
        ])
        
        report = "\n".join(report_lines)
        send_telegram(report)
        print("[+] Weekly report sent.")
        
    except Exception as e:
        print(f"[ERROR] {e}")
        send_telegram(f"❌ 【水晶苍蝇拍 26.3】异常\n错误: {str(e)[:200]}")

if __name__ == "__main__":
    run_weekly_scan()
