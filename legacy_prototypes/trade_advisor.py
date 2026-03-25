import requests
import re
from datetime import datetime

# === CONFIGURATION ===
ETF_CODE = "sh513050"
TENCENT_CODE = "r_hk00700"
TENCENT_SHARES = 8100  # 您持有的腾讯股数
TRADE_RATIO = 0.10     # 建议交易比例 (10%仓位参与套利)
HKD_TO_CNY = 0.92      # 汇率 (港股通会自动折算)

def get_quote_data(codes):
    """
    获取实时五档盘口数据
    codes: ['sh513050', 'r_hk00700']
    """
    url = f"http://qt.gtimg.cn/q={','.join(codes)}"
    try:
        resp = requests.get(url, timeout=3)
        if resp.status_code != 200:
            return None
        content = resp.content.decode('gbk')
        return parse_quote_data(content)
    except Exception as e:
        print(f"Error: {e}")
        return None

def parse_quote_data(raw_text):
    """
    解析五档盘口数据
    """
    result = {}
    
    items = raw_text.strip().split(';')
    for item in items:
        if not item.strip():
            continue
        
        match = re.search(r'v_([a-zA-Z0-9_]+)="(.*)"', item)
        if not match:
            continue
        
        var_name = match.group(1)
        data_str = match.group(2)
        fields = data_str.split('~')
        
        if len(fields) < 50:
            continue
        
        name = fields[1] if len(fields) > 1 else ""
        
        # 解析五档数据
        # 腾讯接口字段:
        # 3=现价, 9=买一价, 10=买一量, 19=卖一价, 20=卖一量
        # 注意: 港股接口字段结构与A股不同
        
        try:
            price = float(fields[3]) if fields[3] else 0
            
            # 尝试解析买一卖一
            bid1_price = float(fields[9]) if fields[9] and fields[9] != '0' else price
            bid1_vol = int(fields[10]) if fields[10] and fields[10] != '0' else 999
            ask1_price = float(fields[19]) if fields[19] and fields[19] != '0' else price
            ask1_vol = int(fields[20]) if fields[20] and fields[20] != '0' else 999
            
            # 如果接口返回的买一卖一价格不合理,使用现价±滑点
            if abs(bid1_price - price) > price * 0.05:
                bid1_price = price * 0.999  # 假设买一比现价低0.1%
                ask1_price = price * 1.001  # 假设卖一比现价高0.1%
                
        except:
            continue
        
        # 解析 IOPV (字段 -7)
        iopv = 0
        try:
            iopv = float(fields[-7])
        except:
            pass
        
        if 'sh513050' in var_name or 'sz' in var_name.lower():
            result['etf'] = {
                'name': name,
                'price': price,
                'iopv': iopv,
                'bid1': {'vol': bid1_vol, 'price': bid1_price},
                'ask1': {'vol': ask1_vol, 'price': ask1_price},
            }
        elif 'hk00700' in var_name.lower():
            result['tencent'] = {
                'name': name,
                'price': price,
                'bid1': {'vol': bid1_vol, 'price': bid1_price},
                'ask1': {'vol': ask1_vol, 'price': ask1_price},
            }
    
    return result

def calculate_trade_advice(data, tencent_shares, trade_ratio):
    """
    计算交易建议
    """
    if 'etf' not in data or 'tencent' not in data:
        return None
    
    etf = data['etf']
    tencent = data['tencent']
    
    # 计算溢价率
    if etf['iopv'] > 0:
        premium = (etf['price'] - etf['iopv']) / etf['iopv'] * 100
    else:
        premium = 0
    
    # 确定交易方向
    if premium < -0.5:
        direction = "折价套利"
        # ETF便宜 -> 买ETF / 卖腾讯
        trade_type = "BUY_ETF_SELL_TENCENT"
    elif premium > 0.5:
        direction = "溢价套利"
        # ETF贵 -> 卖ETF / 买腾讯
        trade_type = "SELL_ETF_BUY_TENCENT"
    else:
        direction = "无操作"
        trade_type = "NONE"
    
    # 计算交易数量
    tencent_trade_shares = int(tencent_shares * trade_ratio)
    # 腾讯每手100股,取整到100
    tencent_trade_shares = (tencent_trade_shares // 100) * 100
    
    if tencent_trade_shares == 0:
        return None
    
    # 计算市值
    # 卖腾讯: 按买一价成交 (有人愿意买)
    # 买ETF: 按卖一价成交 (有人愿意卖)
    
    tencent_sell_price = tencent['bid1']['price']  # 卖出用买一价
    etf_buy_price = etf['ask1']['price']           # 买入用卖一价
    
    # 腾讯市值 (港币 -> 人民币)
    tencent_value_hkd = tencent_trade_shares * tencent_sell_price
    tencent_value_cny = tencent_value_hkd * HKD_TO_CNY
    
    # 对应ETF股数
    etf_shares = int(tencent_value_cny / etf_buy_price)
    # ETF每手100份,取整到100
    etf_shares = (etf_shares // 100) * 100
    
    advice = {
        'time': datetime.now().strftime("%H:%M:%S"),
        'direction': direction,
        'trade_type': trade_type,
        'premium': premium,
        'tencent': {
            'shares': tencent_trade_shares,
            'sell_price': tencent_sell_price,
            'value_hkd': tencent_value_hkd,
            'value_cny': tencent_value_cny,
            'bid1_vol': tencent['bid1']['vol'],
        },
        'etf': {
            'shares': etf_shares,
            'buy_price': etf_buy_price,
            'value_cny': etf_shares * etf_buy_price,
            'ask1_vol': etf['ask1']['vol'],
        },
        'spread': abs(premium),
    }
    
    return advice

def print_advice(advice, data):
    """
    输出交易建议
    """
    if not advice:
        print("当前无明确交易信号")
        return
    
    print("\n" + "=" * 70)
    print(f"【交易建议】 {advice['time']}")
    print("=" * 70)
    
    etf = data['etf']
    tencent = data['tencent']
    
    # 显示盘口
    print(f"\n📊 当前盘口:")
    print(f"  腾讯控股 (00700): {tencent['price']:.2f} HKD")
    print(f"    买一: {tencent['bid1']['price']:.2f} × {tencent['bid1']['vol']}手")
    print(f"    卖一: {tencent['ask1']['price']:.2f} × {tencent['ask1']['vol']}手")
    print(f"\n  中概互联ETF (513050): {etf['price']:.3f} RMB")
    print(f"    买一: {etf['bid1']['price']:.3f} × {etf['bid1']['vol']}手")
    print(f"    卖一: {etf['ask1']['price']:.3f} × {etf['ask1']['vol']}手")
    print(f"    IOPV: {etf['iopv']:.4f} RMB")
    
    print(f"\n📈 溢价率: {advice['premium']:+.2f}%")
    
    if advice['trade_type'] == "BUY_ETF_SELL_TENCENT":
        print(f"\n🟢 套利方向: 折价套利 (ETF便宜)")
        print(f"\n💡 具体操作:")
        print(f"  步骤1: 卖出腾讯")
        print(f"    📤 价格: {advice['tencent']['sell_price']:.2f} HKD")
        print(f"    📤 数量: {advice['tencent']['shares']} 股 ({advice['tencent']['shares']//100}手)")
        print(f"    💰 市值: {advice['tencent']['value_hkd']:,.0f} HKD ≈ {advice['tencent']['value_cny']:,.0f} RMB")
        print(f"\n  步骤2: 买入ETF")
        print(f"    📥 价格: {advice['etf']['buy_price']:.3f} RMB")
        print(f"    📥 数量: {advice['etf']['shares']} 份 ({advice['etf']['shares']//100}手)")
        print(f"    💰 市值: {advice['etf']['value_cny']:,.0f} RMB")
        print(f"\n  预期收益: 约 {advice['spread']:.2f}% (未扣手续费)")
        
    elif advice['trade_type'] == "SELL_ETF_BUY_TENCENT":
        print(f"\n🔴 套利方向: 溢价套利 (ETF贵)")
        print(f"  (您当前无ETF底仓,此方向暂无法操作)")
    else:
        print(f"\n⚪ 当前溢价率较小,建议观望")

def main():
    print("=" * 70)
    print("实时交易建议系统 - 腾讯 vs 中概互联ETF")
    print(f"持有腾讯: {TENCENT_SHARES}股 | 建议交易比例: {TRADE_RATIO*100:.0f}%")
    print("=" * 70)
    
    data = get_quote_data([ETF_CODE, TENCENT_CODE])
    
    if not data or 'etf' not in data or 'tencent' not in data:
        print("数据获取失败,请重试")
        return
    
    advice = calculate_trade_advice(data, TENCENT_SHARES, TRADE_RATIO)
    print_advice(advice, data)

if __name__ == "__main__":
    main()
