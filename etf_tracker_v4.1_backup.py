import time
import subprocess
import requests
from datetime import datetime, timedelta
import json
import os

# --- 配置区 ---
TARGET = "telegram:6228532305"
BASE_PATH = "/root/.openclaw/workspace/AMS/"
LOG_PATH = BASE_PATH + "etf_tracker.log"
DATA_PATH = BASE_PATH + "etf_tracker_data.json"
REPORT_PATH = BASE_PATH + "reports/"

ETF_CODES = [
    "sh513330", "sh513050", "sh513100", "sz159941", 
    "sz159632", "sh513500", "sh513880", "sh513030",
    "sz159501", "sh513110", "sh513730"
]
THRESHOLD_ETF = 0.005  # 0.5%
THRESHOLD_CB = -0.008  # 折价 > 0.8%

# 标记：底层资产不在港股/A股的ETF，由于时差容易产生假溢价
STALE_NAV_CODES = ['sh513050', 'sh513730', 'sh513100', 'sh513500', 'sz159941', 'sz159632', 'sz159501', 'sh513110']

# 美股指数代码 (用于智能诊断)
US_INDEX_CODES = {
    'nasdaq': 'gb_$ndx',
    'spx': 'gb_$spx', 
    'dji': 'gb_$dji'
}

# --- 状态变量 ---
alerted_codes = set()
morning_summary_sent = False
afternoon_summary_sent = False
forced_opening_report_sent = False

def send_msg(text):
    """发送消息到 Telegram"""
    try:
        subprocess.run(["openclaw", "message", "send", "--channel", "telegram", "--target", TARGET, "--message", text], check=True)
        return True
    except Exception as e:
        print(f"Failed to send message: {e}")
        return False

def write_status_data(etfs, cbs=None):
    """写入状态数据到文件"""
    try:
        # 确保目录存在
        os.makedirs(BASE_PATH, exist_ok=True)
        
        data = {
            "timestamp": (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S"),
            "etfs": etfs,
            "convertible_bonds": cbs or []
        }
        with open(DATA_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"Failed to write status data: {e}")

def to_float(val):
    try: return float(val)
    except: return 0.0

def fetch_etf_data():
    """获取ETF实时数据"""
    url = "http://qt.gtimg.cn/q=" + ",".join(ETF_CODES)
    try:
        r = requests.get(url, timeout=10)
        r.encoding = 'gbk'
        lines = r.text.strip().split(';')
        results = []
        for line in lines:
            if not line.strip(): continue
            try:
                data = line.split('=')[1].strip('"')
                fields = data.split('~')
                if len(fields) < 80: continue
                name, code = fields[1], fields[2]
                bid1, ask1, iopv = to_float(fields[9]), to_float(fields[19]), to_float(fields[78])
                if iopv <= 0: continue
                premium = (ask1 / iopv - 1) if ask1 > 0 else 0
                discount = (1 - bid1 / iopv) if bid1 > 0 else 0
                diff_val = premium if premium > 0 else -discount
                results.append({"code": code, "name": name, "bid1": bid1, "ask1": ask1, "iopv": iopv, "diff": diff_val, "is_stale": code in STALE_NAV_CODES})
            except: continue
        results.sort(key=lambda x: x['diff'], reverse=True)
        return results
    except: return []

def fetch_cb_data():
    """获取可转债数据"""
    url = 'https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=50&po=0&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f243&fs=b:MK0354,b:MK0355&fields=f12,f14,f2,f3,f243,f244'
    try:
        r = requests.get(url, timeout=10)
        items = r.json().get('data', {}).get('diff', [])
        results = []
        for i in items:
            code, name, price, prem_raw = i['f12'], i['f14'], to_float(i['f2']), i.get('f243')
            if isinstance(prem_raw, (int, float)):
                results.append({"code": code, "name": name, "price": price, "premium": prem_raw / 100.0})
        return results
    except: return []

def fetch_us_index_data():
    """获取美股指数数据（用于智能诊断）"""
    results = {}
    for name, code in US_INDEX_CODES.items():
        try:
            url = f"http://qt.gtimg.cn/q={code}"
            r = requests.get(url, timeout=5)
            r.encoding = 'gbk'
            if '~' in r.text:
                fields = r.text.split('~')
                if len(fields) > 5:
                    # f3 = 涨跌幅
                    change_pct = to_float(fields[3]) if len(fields) > 3 else 0
                    results[name] = {
                        'change_pct': change_pct,
                        'status': '休市' if abs(change_pct) < 0.01 else '正常'
                    }
        except:
            pass
    return results

def format_pct(val):
    return f"{'+' if val > 0 else ''}{val*100:.2f}%"

def is_trading_day():
    now = datetime.utcnow() + timedelta(hours=8)
    if now.weekday() >= 5: return False
    return True

def get_reasoning(code, diff, us_data=None):
    """【智能分析】根据代码和偏离度给出原因分析"""
    if code in STALE_NAV_CODES and diff < -0.003:
        # 获取美股数据
        nasdaq_change = us_data.get('nasdaq', {}).get('change_pct', 0) if us_data else 0
        
        if nasdaq_change < -1:
            return f"\n🧐 分析: 折价反映隔夜美股下跌预期(纳指{nasdaq_change:.2f}%)，非纯套利机会。"
        elif nasdaq_change > 0.5:
            return f"\n🧐 分析: 美股隔夜上涨(纳指+{nasdaq_change:.2f}%)，当前折价可能是套利窗口，建议关注申购通道。"
        else:
            return "\n🧐 分析: 当前折价可能系 Pricing-in 隔夜美股预期，需等待净值更新后重新评估。"
    
    if diff > 0.01:
        return "\n🧐 分析: 溢价极高，请务必确认 QDII 申购通道是否关闭。"
    
    return ""

def generate_full_report(etfs=None, cbs=None, us_data=None):
    """
    生成全功能分析报告
    返回: 报告内容字符串
    """
    # 获取数据
    if etfs is None:
        etfs = fetch_etf_data()
    if cbs is None:
        cbs = fetch_cb_data()
    if us_data is None:
        us_data = fetch_us_index_data()
    
    timestamp = (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")
    
    # 构建报告
    report_lines = [
        "🔔 【AMS 全功能分析报告】",
        f"📅 时间: {timestamp}",
        "━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "📊 【实时ETF数据】",
        "| 名称 | 代码 | 现价 | 净值 | 折溢价 |",
        "|------|------|------|------|--------|"
    ]
    
    # ETF数据行
    for e in etfs[:8]:
        report_lines.append(f"| {e['name']} | {e['code']} | {e['ask1']:.3f} | {e['iopv']:.3f} | {format_pct(e['diff'])} |")
    
    # 折价品种诊断
    report_lines.extend(["", "📉 【折价品种诊断】"])
    discount_etfs = [e for e in etfs if e['diff'] < -0.005]
    if discount_etfs:
        for e in discount_etfs[:3]:
            reasoning = get_reasoning(e['code'], e['diff'], us_data)
            report_lines.append(f"• {e['name']}({e['code']}): 折价{format_pct(e['diff'])}{reasoning}")
    else:
        report_lines.append("当前无明显折价品种")
    
    # 溢价品种监控
    report_lines.extend(["", "📈 【溢价品种监控】"])
    premium_etfs = [e for e in etfs if e['diff'] > 0.005]
    if premium_etfs:
        for e in premium_etfs[:3]:
            reasoning = get_reasoning(e['code'], e['diff'], us_data)
            report_lines.append(f"• {e['name']}({e['code']}): 溢价{format_pct(e['diff'])}{reasoning}")
    else:
        report_lines.append("当前无明显溢价品种")
    
    # 分析建议
    report_lines.extend(["", "💡 【分析建议】"])
    if discount_etfs:
        report_lines.append("1. 折价品种建议关注申购通道开放情况，确认是否存在真实套利窗口。")
    if premium_etfs:
        report_lines.append("2. 溢价品种建议检查赎回通道，评估是否可进行溢价套利。")
    if not discount_etfs and not premium_etfs:
        report_lines.append("当前市场折溢价水平正常，建议保持监控状态。")
    report_lines.append("3. 美股指数变动可能影响次日ETF净值估算，请密切关注。")
    
    report_lines.extend([
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━",
        f"⚡ 数据更新于 {timestamp}"
    ])
    
    return "\n".join(report_lines)

def generate_test_report():
    """
    【测试报告触发方法】
    供总管随时通过命令触发的报告生成方法
    返回: (report_content, success)
    """
    try:
        print("[TEST REPORT] 开始生成测试报告...")
        
        # 1. 获取实时数据
        etfs = fetch_etf_data()
        cbs = fetch_cb_data()
        us_data = fetch_us_index_data()
        
        # 2. 写入状态
        write_status_data(etfs, cbs)
        
        # 3. 生成报告
        report = generate_full_report(etfs, cbs, us_data)
        
        # 4. 发送到 Telegram
        send_success = send_msg(report)
        
        # 5. 保存报告到文件
        os.makedirs(REPORT_PATH, exist_ok=True)
        report_filename = f"report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"
        report_filepath = REPORT_PATH + report_filename
        with open(report_filepath, 'w', encoding='utf-8') as f:
            f.write(report)
        
        print(f"[TEST REPORT] 报告已生成: {report_filepath}")
        print(f"[TEST REPORT] Telegram发送: {'成功' if send_success else '失败'}")
        
        return report, send_success
        
    except Exception as e:
        print(f"[TEST REPORT] 生成失败: {e}")
        return f"报告生成失败: {e}", False

def run_tracker():
    """主运行循环"""
    global morning_summary_sent, afternoon_summary_sent, forced_opening_report_sent
    print("QBot AMS (Arbitrage Monitoring System) V4.1 Started.")
    
    # 确保目录存在
    os.makedirs(BASE_PATH, exist_ok=True)
    os.makedirs(REPORT_PATH, exist_ok=True)
    
    while True:
        try:
            if not is_trading_day():
                time.sleep(3600); continue
            
            now = datetime.utcnow() + timedelta(hours=8)
            current_time = now.strftime("%H:%M")
            
            # 1. 开盘强行播报
            if "09:26" <= current_time <= "11:30" and not forced_opening_report_sent:
                etfs = fetch_etf_data()
                cbs = fetch_cb_data()
                us_data = fetch_us_index_data()
                write_status_data(etfs, cbs)
                msg = f"🔔 【AMS 开盘数据】({current_time})\n"
                for e in etfs[:3]:
                    reasoning = get_reasoning(e['code'], e['diff'], us_data)
                    msg += f"• {e['name']}: {format_pct(e['diff'])}{reasoning}\n"
                send_msg(msg)
                forced_opening_report_sent = True

            # 2. 实时异动告警
            if ("09:30" <= current_time <= "11:30") or ("13:00" <= current_time <= "15:00"):
                etfs = fetch_etf_data()
                us_data = fetch_us_index_data()
                for e in etfs:
                    if abs(e['diff']) >= THRESHOLD_ETF and e['code'] not in alerted_codes:
                        alerted_codes.add(e['code'])
                        icon = "🔴" if e['diff'] > 0 else "🟢"
                        reasoning = get_reasoning(e['code'], e['diff'], us_data)
                        send_msg(f"{icon} 【AMS 异动捕捉】\n标的: {e['name']}\n幅度: {format_pct(e['diff'])}{reasoning}")

            # 3. 收盘总结 (使用全功能报告)
            if "15:05" <= current_time <= "15:15" and not afternoon_summary_sent:
                report, _ = generate_test_report()
                afternoon_summary_sent = True

            # 4. 零点重置
            if current_time == "00:00":
                forced_opening_report_sent = False; alerted_codes.clear(); afternoon_summary_sent = False
                
            time.sleep(30)
        except Exception as e:
            print(f"Loop error: {e}"); time.sleep(10)

if __name__ == '__main__':
    # 支持命令行参数触发测试报告
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--test-report':
        report, success = generate_test_report()
        print("\n" + "="*50)
        print("测试报告内容:")
        print("="*50)
        print(report)
        print("="*50)
        print(f"状态: {'成功' if success else '失败'}")
    else:
        run_tracker()
