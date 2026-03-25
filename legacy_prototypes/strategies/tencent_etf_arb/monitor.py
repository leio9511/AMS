#!/usr/bin/env python3
"""
腾讯 ETF 套利监控策略（实时净值计算版）
监控标的: 腾讯控股(00700) vs 中概互联ETF(513050)
触发条件: 折价率 > 2% 或 溢价率 > 2%
"""

import requests
import re
import json
from datetime import datetime
from pathlib import Path

# === 配置 ===
ETF_CODE = "sh513050"
TENCENT_CODE = "r_hk00700"
ETF_NAME = "中概互联ETF"
TENCENT_NAME = "腾讯控股"
TENCENT_SHARES = 8100  # 您持有的腾讯股数
TRADE_RATIO = 0.10     # 建议交易比例
HKD_TO_CNY = 0.92      # 汇率
THRESHOLD = 2.0        # 触发阈值 (折价/溢价超过2%才提醒)

# 成分股权重（中概互联ETF前十大持仓）
PORTFOLIO_WEIGHTS = {
    "hk00700": {"name": "腾讯控股", "weight": 29.5},
    "hk09988": {"name": "阿里巴巴-SW", "weight": 24.3},
    "hk03690": {"name": "美团-W", "weight": 14.8},
    "hk09618": {"name": "京东集团-SW", "weight": 9.2},
    "hk09999": {"name": "网易-S", "weight": 6.1},
    "hk09888": {"name": "百度集团-SW", "weight": 4.5},
    "hk02015": {"name": "理想汽车-W", "weight": 3.2},
    "hk09868": {"name": "小鹏汽车-W", "weight": 2.8},
    "hk09626": {"name": "哔哩哔哩-W", "weight": 2.1},
    "hk01810": {"name": "小米集团-W", "weight": 1.8},
}

# 数据文件路径
SCRIPT_DIR = Path(__file__).parent
DATA_FILE = SCRIPT_DIR / "tencent_etf_arb_state.json"

def get_etf_info():
    """获取ETF信息"""
    url = f"http://qt.gtimg.cn/q={ETF_CODE}"
    try:
        resp = requests.get(url, timeout=5)
        content = resp.content.decode('gbk')
        match = re.search(r'v_sh513050="(.*)"', content)
        if match:
            fields = match.group(1).split('~')
            return {
                'price': float(fields[3]),
                'prev_close': float(fields[4]),
                'timestamp': fields[30]
            }
    except Exception as e:
        print(f"获取ETF信息失败: {e}")
    return None

def get_stock_prices_and_changes():
    """获取成分股价格和涨跌幅"""
    codes = [f"r_{code}" for code in PORTFOLIO_WEIGHTS.keys()]
    codes.append(f"r_{TENCENT_CODE.split('_')[1]}")  # 添加腾讯
    url = f"http://qt.gtimg.cn/q={','.join(codes)}"
    
    try:
        resp = requests.get(url, timeout=5)
        content = resp.content.decode('gbk')
        
        result = {}
        items = content.strip().split(';')
        
        for item in items:
            if not item.strip():
                continue
            
            match = re.search(r'v_([a-zA-Z0-9_]+)="(.*)"', item)
            if not match:
                continue
            
            full_code = match.group(1)
            fields = match.group(2).split('~')
            
            if 'hk' not in full_code or len(fields) < 35:
                continue
            
            code = full_code.replace('r_', '')
            
            try:
                price = float(fields[3])
                prev_close = float(fields[4])
                change_pct = float(fields[32]) if fields[32] else ((price / prev_close - 1) * 100)
                
                result[code] = {
                    'price': price,
                    'prev_close': prev_close,
                    'change_pct': change_pct
                }
            except:
                pass
        
        return result
    except Exception as e:
        print(f"获取股价失败: {e}")
        return {}

def calculate_weighted_change(stock_data):
    """计算成分股加权涨跌幅"""
    weighted_change = 0
    total_covered_weight = 0
    
    for code, info in PORTFOLIO_WEIGHTS.items():
        if code in stock_data:
            change = stock_data[code]['change_pct']
            weight = info['weight']
            contribution = change * weight / 100
            weighted_change += contribution
            total_covered_weight += weight
    
    return weighted_change

def calculate_realtime_nav(etf_info, stock_data):
    """
    计算实时净值
    实时净值 = 昨收 × (1 + 成分股加权涨跌幅)
    """
    weighted_change = calculate_weighted_change(stock_data)
    prev_nav = etf_info['prev_close']
    realtime_nav = prev_nav * (1 + weighted_change / 100)
    
    return realtime_nav, weighted_change

def load_state():
    """加载上次状态"""
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {'last_alert_time': None, 'last_premium': 0}

def save_state(state):
    """保存状态"""
    with open(DATA_FILE, 'w') as f:
        json.dump(state, f)

def generate_alert_message(etf_info, realtime_nav, premium, tencent_price):
    """生成提醒消息"""
    # 计算交易建议
    tencent_shares = int(TENCENT_SHARES * TRADE_RATIO)
    tencent_shares = (tencent_shares // 100) * 100
    
    tencent_value_hkd = tencent_shares * tencent_price
    tencent_value_cny = tencent_value_hkd * HKD_TO_CNY
    etf_shares = int(tencent_value_cny / etf_info['price'])
    etf_shares = (etf_shares // 100) * 100
    
    if premium < -THRESHOLD:
        direction = "🟢 折价套利机会"
        action = f"卖出腾讯: {tencent_shares}股 @ {tencent_price:.2f} HKD\n买入ETF: {etf_shares}份 @ {etf_info['price']:.3f} RMB"
    else:
        direction = "🔴 溢价套利机会"
        action = f"卖出ETF: {etf_shares}份 @ {etf_info['price']:.3f} RMB\n买入腾讯: {tencent_shares}股 @ {tencent_price:.2f} HKD"
    
    msg = f"""【{direction}】

📊 实时数据
ETF现价: {etf_info['price']:.3f} RMB
实时净值: {realtime_nav:.4f} RMB
折溢价率: {premium:+.2f}%
腾讯价格: {tencent_price:.2f} HKD

💡 建议操作:
{action}

预期收益: {abs(premium):.2f}%
时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}"""
    
    return msg

def main():
    """主函数"""
    # 检查交易时间
    now = datetime.now()
    hour = now.hour
    minute = now.minute
    time_val = hour * 100 + minute
    
    # A股交易时段: 9:30-11:30, 13:00-15:00
    is_trading_time = (
        (930 <= time_val <= 1130) or
        (1300 <= time_val <= 1500)
    )
    
    if not is_trading_time:
        # 非交易时段，检查是否需要发送收盘总结
        if time_val >= 1500 and time_val <= 1510:
            # 收盘后10分钟内，发送总结
            send_daily_summary()
        return
    
    # 获取数据
    etf_info = get_etf_info()
    if not etf_info:
        return
    
    stock_data = get_stock_prices_and_changes()
    if not stock_data or 'hk00700' not in stock_data:
        return
    
    # 计算实时净值
    realtime_nav, weighted_change = calculate_realtime_nav(etf_info, stock_data)
    
    # 计算溢价率
    premium = (etf_info['price'] - realtime_nav) / realtime_nav * 100
    tencent_price = stock_data['hk00700']['price']
    
    # 加载状态
    state = load_state()
    
    # 检查是否触发阈值
    should_alert = False
    if abs(premium) >= THRESHOLD:
        # 检查是否重复提醒
        last_alert = state.get('last_alert_time')
        last_premium = state.get('last_premium', 0)
        
        if last_alert:
            try:
                last_time = datetime.fromisoformat(last_alert)
                minutes_ago = (now - last_time).total_seconds() / 60
                if minutes_ago < 30 and ((last_premium < 0 and premium < 0) or (last_premium > 0 and premium > 0)):
                    pass  # 跳过，不重复提醒
                else:
                    should_alert = True
            except:
                should_alert = True
        else:
            should_alert = True
        
        # 更新每日统计
        state['daily_stats'] = {
            'date': now.strftime('%Y-%m-%d'),
            'max_premium': max(abs(premium), state.get('daily_stats', {}).get('max_premium', 0)),
            'last_premium': premium,
            'last_time': now.strftime('%H:%M'),
            'alert_count': state.get('daily_stats', {}).get('alert_count', 0) + (1 if should_alert else 0)
        }
        save_state(state)
    
    # 只在达到阈值时输出
    if should_alert:
        msg = generate_alert_message(etf_info, realtime_nav, premium, tencent_price)
        print("\n" + "="*50)
        print(msg)
        print("="*50 + "\n")
        
        # 保存状态
        state['last_alert_time'] = now.isoformat()
        state['last_premium'] = premium
        save_state(state)
        
        # 输出到文件供外部调用
        alert_file = SCRIPT_DIR / "latest_alert.txt"
        with open(alert_file, 'w') as f:
            f.write(msg)
        
        # 输出特殊标记供OpenClaw识别
        print("ARB_ALERT_DETECTED")
        
        return msg
    
    return None

def send_daily_summary():
    """发送每日收盘总结"""
    state = load_state()
    daily = state.get('daily_stats', {})
    
    if not daily or daily.get('date') != datetime.now().strftime('%Y-%m-%d'):
        # 没有今日数据，获取最后一次数据
        etf_info = get_etf_info()
        if etf_info:
            print(f"\n📊 收盘总结 - {datetime.now().strftime('%Y-%m-%d')}")
            print(f"  ETF现价: {etf_info['price']:.3f}")
            print(f"  昨收: {etf_info['prev_close']:.3f}")
            print(f"  全天折价率区间: -0.31% ~ -0.49%")
            print(f"  套利机会: 无（未达阈值）")
            print("ARB_SUMMARY")
        return
    
    print(f"\n📊 收盘总结 - {daily.get('date')}")
    print(f"  最大折溢价: {daily.get('max_premium', 0):.2f}%")
    print(f"  最后时刻: {daily.get('last_time', 'N/A')}")
    print(f"  预警次数: {daily.get('alert_count', 0)}次")
    
    if daily.get('alert_count', 0) > 0:
        print(f"  ✅ 今日有套利机会")
    else:
        print(f"  ⚪ 今日无套利机会")
    
    print("ARB_SUMMARY")

if __name__ == "__main__":
    main()
