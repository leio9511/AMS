#!/usr/bin/env python3
"""
跨境ETF折价套利决策工具
提供：实时净值 + 五档盘口 + 期货对冲信息 + 交易建议
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from cross_border_etf_monitor import ETFArbMonitor, CORE_ETFS
from datetime import datetime

# ETF对应的期货合约映射
FUTURES_MAPPING = {
    # 港股指数期货
    "恒生指数": {
        "futures_code": "HSI",
        "exchange": "HKEX",
        "multiplier": 50,  # 每点50港币
        "description": "恒生指数期货（大期）",
        "mini_code": "MHI",  # 小期
        "mini_multiplier": 10,  # 每点10港币
    },
    "恒生科技": {
        "futures_code": "HTI",
        "exchange": "HKEX",
        "multiplier": 50,
        "description": "恒生科技指数期货",
        "mini_code": "MHT",
        "mini_multiplier": 10,
    },
    "恒生国企": {
        "futures_code": "HHI",
        "exchange": "HKEX",
        "multiplier": 50,
        "description": "恒生中国企业指数期货",
        "mini_code": "MCH",
        "mini_multiplier": 10,
    },
    "中概互联": {
        "futures_code": None,  # 无直接对应期货
        "exchange": None,
        "description": "无对应期货，建议用恒生科技期货对冲（相关性80%+）",
        "alternative": "恒生科技",
    },
    "恒生互联网": {
        "futures_code": None,
        "exchange": None,
        "description": "无直接对应期货，建议用恒生科技期货对冲",
        "alternative": "恒生科技",
    },
    
    # 美股指数期货
    "纳斯达克100": {
        "futures_code": "NQ",
        "exchange": "CME",
        "multiplier": 20,  # 每点20美元
        "description": "纳斯达克100期货（E-mini）",
        "mini_code": "MNQ",  # 微型期货
        "mini_multiplier": 2,
    },
    "标普500": {
        "futures_code": "ES",
        "exchange": "CME",
        "multiplier": 50,
        "description": "标普500期货（E-mini）",
        "mini_code": "MES",
        "mini_multiplier": 5,
    },
    "纳斯达克科技": {
        "futures_code": None,
        "exchange": None,
        "description": "无直接对应期货，建议用纳斯达克100期货对冲",
        "alternative": "纳斯达克100",
    },
    
    # 日本指数期货
    "日经225": {
        "futures_code": "NK",
        "exchange": "OSE/CME",
        "multiplier": 500,  # 日经期货每点500日元
        "description": "日经225期货（大阪/芝商所）",
        "mini_code": "NKD",  # 美元计价版
        "mini_multiplier": 5,
    },
    
    # 欧洲指数期货
    "DAX": {
        "futures_code": "FDAX",
        "exchange": "Eurex",
        "multiplier": 25,
        "description": "德国DAX期货",
    },
    "CAC40": {
        "futures_code": "FCE",
        "exchange": "Euronext",
        "multiplier": 10,
        "description": "法国CAC40期货",
    },
}

class ETFArbAdvisor:
    """ETF套利决策顾问"""
    
    def __init__(self):
        self.monitor = ETFArbMonitor()
    
    def analyze_etf(self, etf_code, threshold=1.0):
        """
        分析单个ETF的套利机会
        """
        if etf_code not in CORE_ETFS:
            print(f"未找到ETF: {etf_code}")
            return None
        
        etf_info = CORE_ETFS[etf_code]
        
        # 获取行情
        quote = self.monitor.get_etf_quote(etf_code)
        if not quote:
            print(f"无法获取 {etf_code} 的行情数据")
            return None
        
        # 获取期货信息
        index_name = etf_info['index']
        futures_info = FUTURES_MAPPING.get(index_name, {})
        
        # 计算净值（如果有权重）
        realtime_nav, weighted_change = self.monitor.calculate_realtime_nav(etf_code, quote)
        
        if realtime_nav:
            premium = (quote['price'] - realtime_nav) / realtime_nav * 100
        else:
            realtime_nav = quote['prev_close']
            premium = 0
        
        # 输出分析
        print("\n" + "=" * 70)
        print(f"【ETF套利分析】{etf_info['name']} ({etf_code})")
        print("=" * 70)
        
        print(f"\n📊 实时行情：")
        print(f"  现价：{quote['price']:.3f} RMB")
        print(f"  昨收：{quote['prev_close']:.3f} RMB")
        print(f"  实时净值：{realtime_nav:.3f} RMB")
        print(f"  溢价率：{premium:+.2f}%")
        
        print(f"\n📈 五档盘口：")
        print(f"  卖5：{quote['ask5']:.3f} × {quote['ask5_vol']}手")
        print(f"  卖4：{quote['ask4']:.3f} × {quote['ask4_vol']}手")
        print(f"  卖3：{quote['ask3']:.3f} × {quote['ask3_vol']}手")
        print(f"  卖2：{quote['ask2']:.3f} × {quote['ask2_vol']}手")
        print(f"  卖1：{quote['ask1']:.3f} × {quote['ask1_vol']}手")
        print(f"  ─────────────────────")
        print(f"  买1：{quote['bid1']:.3f} × {quote['bid1_vol']}手")
        print(f"  买2：{quote['bid2']:.3f} × {quote['bid2_vol']}手")
        print(f"  买3：{quote['bid3']:.3f} × {quote['bid3_vol']}手")
        print(f"  买4：{quote['bid4']:.3f} × {quote['bid4_vol']}手")
        print(f"  买5：{quote['bid5']:.3f} × {quote['bid5_vol']}手")
        
        print(f"\n🎯 对冲期货：")
        if futures_info:
            print(f"  指数：{index_name}")
            print(f"  期货：{futures_info['futures_code']} ({futures_info['description']})")
            if 'multiplier' in futures_info:
                print(f"  合约乘数：{futures_info['multiplier']}")
            if 'mini_code' in futures_info:
                print(f"  小型合约：{futures_info['mini_code']}")
        else:
            print(f"  暂无对应期货合约")
        
        # 套利建议
        if abs(premium) >= threshold:
            print(f"\n💡 套利建议：")
            
            if premium < -threshold:
                # 折价套利
                print(f"  【折价套利机会】折价 {-premium:.2f}%")
                print(f"  操作步骤：")
                print(f"  1. 买入ETF：{quote['ask1_vol']}手 @ {quote['ask1']:.3f} RMB")
                print(f"  2. 做空期货：{futures_info.get('futures_code', 'N/A')}")
                print(f"  3. 等待溢价回归后平仓")
                print(f"\n  预期收益：{-premium:.2f}%（未扣手续费）")
            else:
                # 溢价套利
                print(f"  【溢价套利机会】溢价 {premium:.2f}%")
                print(f"  操作步骤：")
                print(f"  1. 卖出ETF：{quote['bid1_vol']}手 @ {quote['bid1']:.3f} RMB")
                print(f"  2. 做多期货：{futures_info.get('futures_code', 'N/A')}")
                print(f"  3. 等待折价回归后平仓")
                print(f"\n  预期收益：{premium:.2f}%（未扣手续费）")
        else:
            print(f"\n⚪ 折溢价率 {premium:+.2f}% < {threshold}%，暂无套利空间")
        
        print("\n" + "=" * 70)
        
        return {
            'etf_code': etf_code,
            'quote': quote,
            'nav': realtime_nav,
            'premium': premium,
            'futures': futures_info,
        }
    
    def scan_all(self, threshold=1.5):
        """
        扫描所有ETF的套利机会
        """
        print("\n" + "=" * 80)
        print(f"跨境ETF套利机会扫描 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        
        opportunities = self.monitor.monitor_all(threshold=threshold)
        
        if opportunities:
            print(f"\n发现 {len(opportunities)} 个套利机会，详细信息：")
            for opp in opportunities:
                self.analyze_etf(opp['code'], threshold)
        
        return opportunities

def main():
    advisor = ETFArbAdvisor()
    
    # 示例：分析中概互联ETF
    if len(sys.argv) > 1:
        etf_code = sys.argv[1]
        advisor.analyze_etf(etf_code, threshold=1.0)
    else:
        # 扫描所有ETF
        advisor.scan_all(threshold=1.5)

if __name__ == "__main__":
    main()
