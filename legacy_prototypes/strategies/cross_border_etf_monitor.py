#!/usr/bin/env python3
"""
跨境ETF实时净值+五档盘口监控
支持港股、美股、日本等跨境ETF
"""

import requests
import re
import json
from datetime import datetime
from pathlib import Path
import time

# === 核心跨境ETF池（适合套利的高流动性品种）===
CORE_ETFS = {
    # 港股类
    "sh513050": {"name": "中概互联", "type": "港股", "index": "中概互联"},
    "sh513180": {"name": "恒生科技", "type": "港股", "index": "恒生科技"},
    "sz159920": {"name": "恒生ETF", "type": "港股", "index": "恒生指数"},
    "sh510900": {"name": "恒生国企", "type": "港股", "index": "恒生国企"},
    "sh513330": {"name": "恒生互联网", "type": "港股", "index": "恒生互联网"},
    "sh513060": {"name": "恒生医疗", "type": "港股", "index": "恒生医疗"},
    "sh513020": {"name": "港股通科技", "type": "港股", "index": "港股通科技"},
    "sh513010": {"name": "恒生科技易方达", "type": "港股", "index": "恒生科技"},
    
    # 美股类
    "sh513100": {"name": "纳指100国泰", "type": "美股", "index": "纳斯达克100"},
    "sz159941": {"name": "纳指100广发", "type": "美股", "index": "纳斯达克100"},
    "sz159696": {"name": "纳指100易方达", "type": "美股", "index": "纳斯达克100"},
    "sh513500": {"name": "标普500", "type": "美股", "index": "标普500"},
    "sz159655": {"name": "标普500华夏", "type": "美股", "index": "标普500"},
    "sz159509": {"name": "纳指科技", "type": "美股", "index": "纳斯达克科技"},
    
    # 日本类
    "sh513520": {"name": "日经225华夏", "type": "日本", "index": "日经225"},
    "sh513880": {"name": "日经225华安", "type": "日本", "index": "日经225"},
    
    # 欧洲类
    "sh513030": {"name": "德国DAX", "type": "欧洲", "index": "DAX"},
    "sh513080": {"name": "法国CAC40", "type": "欧洲", "index": "CAC40"},
}

# 成分股权重数据（关键ETF）
# 数据来源：基金季报，需定期更新
ETF_WEIGHTS = {
    "sh513050": {  # 中概互联
        "hk00700": {"name": "腾讯控股", "weight": 29.5},
        "hk09988": {"name": "阿里巴巴", "weight": 24.3},
        "hk03690": {"name": "美团", "weight": 14.8},
        "hk09618": {"name": "京东", "weight": 9.2},
        "hk09999": {"name": "网易", "weight": 6.1},
        "hk09888": {"name": "百度", "weight": 4.5},
        "hk02015": {"name": "理想汽车", "weight": 3.2},
        "hk09868": {"name": "小鹏汽车", "weight": 2.8},
        "hk09626": {"name": "哔哩哔哩", "weight": 2.1},
        "hk01810": {"name": "小米", "weight": 1.8},
    },
    "sh513180": {  # 恒生科技
        "hk00700": {"name": "腾讯控股", "weight": 8.5},
        "hk09988": {"name": "阿里巴巴", "weight": 8.2},
        "hk03690": {"name": "美团", "weight": 8.0},
        "hk01810": {"name": "小米", "weight": 7.8},
        "hk09618": {"name": "京东", "weight": 5.5},
        "hk09999": {"name": "网易", "weight": 4.5},
        "hk09888": {"name": "百度", "weight": 4.0},
        "hk09868": {"name": "小鹏汽车", "weight": 3.8},
        "hk09626": {"name": "哔哩哔哩", "weight": 3.5},
        "hk02015": {"name": "理想汽车", "weight": 3.2},
        "hk03692": {"name": "联想集团", "weight": 2.8},
        "hk02382": {"name": "舜宇光学", "weight": 2.5},
        "hk00285": {"name": "比亚迪电子", "weight": 2.3},
        "hk00268": {"name": "金蝶国际", "weight": 2.0},
        "hk01347": {"name": "华虹半导体", "weight": 1.8},
        "hk00981": {"name": "中芯国际", "weight": 1.5},
        "hk00241": {"name": "阿里健康", "weight": 1.3},
        "hk06060": {"name": "众安在线", "weight": 1.2},
        "hk02057": {"name": "浙江世宝", "weight": 1.0},
        "hk01211": {"name": "比亚迪股份", "weight": 0.8},
    },
}

class ETFArbMonitor:
    """ETF套利监控器"""
    
    def __init__(self):
        self.cache_dir = Path(__file__).parent / "cache"
        self.cache_dir.mkdir(exist_ok=True)
        
    def get_etf_quote(self, etf_code):
        """
        获取ETF五档行情
        返回：{price, prev_close, bid1, ask1, bid1_vol, ask1_vol, ...}
        """
        url = f"http://qt.gtimg.cn/q={etf_code}"
        try:
            resp = requests.get(url, timeout=5)
            content = resp.content.decode('gbk')
            
            match = re.search(r'v_([a-zA-Z0-9]+)="(.*)"', content)
            if not match:
                return None
            
            fields = match.group(2).split('~')
            
            # 解析五档
            # 字段：3=现价, 4=昨收, 9=买一价, 10=买一量, 19=卖一价, 20=卖一量
            quote = {
                'code': etf_code,
                'name': fields[1],
                'price': float(fields[3]) if fields[3] else 0,
                'prev_close': float(fields[4]) if fields[4] else 0,
                'bid1': float(fields[9]) if fields[9] and fields[9] != '0' else 0,
                'bid1_vol': int(fields[10]) if fields[10] and fields[10] != '0' else 0,
                'bid2': float(fields[11]) if len(fields) > 11 and fields[11] else 0,
                'bid2_vol': int(fields[12]) if len(fields) > 12 and fields[12] else 0,
                'bid3': float(fields[13]) if len(fields) > 13 and fields[13] else 0,
                'bid3_vol': int(fields[14]) if len(fields) > 14 and fields[14] else 0,
                'bid4': float(fields[15]) if len(fields) > 15 and fields[15] else 0,
                'bid4_vol': int(fields[16]) if len(fields) > 16 and fields[16] else 0,
                'bid5': float(fields[17]) if len(fields) > 17 and fields[17] else 0,
                'bid5_vol': int(fields[18]) if len(fields) > 18 and fields[18] else 0,
                'ask1': float(fields[19]) if len(fields) > 19 and fields[19] and fields[19] != '0' else 0,
                'ask1_vol': int(fields[20]) if len(fields) > 20 and fields[20] and fields[20] != '0' else 0,
                'ask2': float(fields[21]) if len(fields) > 21 and fields[21] else 0,
                'ask2_vol': int(fields[22]) if len(fields) > 22 and fields[22] else 0,
                'ask3': float(fields[23]) if len(fields) > 23 and fields[23] else 0,
                'ask3_vol': int(fields[24]) if len(fields) > 24 and fields[24] else 0,
                'ask4': float(fields[25]) if len(fields) > 25 and fields[25] else 0,
                'ask4_vol': int(fields[26]) if len(fields) > 26 and fields[26] else 0,
                'ask5': float(fields[27]) if len(fields) > 27 and fields[27] else 0,
                'ask5_vol': int(fields[28]) if len(fields) > 28 and fields[28] else 0,
                'timestamp': fields[30] if len(fields) > 30 else '',
            }
            
            # 如果买一卖一价格为0，使用现价
            if quote['bid1'] == 0:
                quote['bid1'] = quote['price']
            if quote['ask1'] == 0:
                quote['ask1'] = quote['price']
            
            return quote
            
        except Exception as e:
            print(f"获取 {etf_code} 行情失败: {e}")
            return None
    
    def get_stock_prices(self, stock_codes):
        """
        批量获取股票实时价格
        stock_codes: ['hk00700', 'hk09988', ...]
        返回：{code: {price, change_pct}}
        """
        # 构建请求代码
        codes = [f"r_{code}" for code in stock_codes]
        url = f"http://qt.gtimg.cn/q={','.join(codes)}"
        
        try:
            resp = requests.get(url, timeout=10)
            content = resp.content.decode('gbk')
            
            result = {}
            items = content.strip().split(';')
            
            for item in items:
                if not item.strip():
                    continue
                
                match = re.search(r'v_([a-zA-Z0-9_]+)="(.*)"', item)
                if not match:
                    continue
                
                full_code = match.group(1)  # r_hk00700
                fields = match.group(2).split('~')
                
                if 'hk' not in full_code or len(fields) < 35:
                    continue
                
                code = full_code.replace('r_', '')  # hk00700
                
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
    
    def calculate_realtime_nav(self, etf_code, quote):
        """
        计算ETF实时净值
        方法：基于成分股加权涨跌幅
        """
        if etf_code not in ETF_WEIGHTS:
            return None, 0
        
        weights = ETF_WEIGHTS[etf_code]
        stock_codes = list(weights.keys())
        
        # 获取成分股价格
        stock_data = self.get_stock_prices(stock_codes)
        if not stock_data:
            return None, 0
        
        # 计算加权涨跌幅
        weighted_change = 0
        total_weight = 0
        
        for code, info in weights.items():
            if code in stock_data:
                change = stock_data[code]['change_pct']
                weight = info['weight']
                weighted_change += change * weight / 100
                total_weight += weight
        
        # 计算实时净值
        prev_nav = quote['prev_close']
        realtime_nav = prev_nav * (1 + weighted_change / 100)
        
        return realtime_nav, weighted_change
    
    def get_etf_from_eastmoney(self, etf_code):
        """
        从东方财富获取ETF数据（备用方案）
        注意：东方财富的IOPV数据不稳定，仅供参考
        返回：{price, iopv, premium}
        """
        # 转换代码格式
        if etf_code.startswith('sh'):
            secid = f"1.{etf_code[2:]}"
        elif etf_code.startswith('sz'):
            secid = f"0.{etf_code[2:]}"
        else:
            return None
        
        url = "http://push2.eastmoney.com/api/qt/stock/get"
        params = {
            "secid": secid,
            "fields": "f43,f57,f58,f60,f170,f171,f44,f45,f46"
        }
        
        try:
            resp = requests.get(url, params=params, timeout=5)
            data = resp.json()
            
            if data and 'data' in data and data['data']:
                d = data['data']
                price = d.get('f43', 0) / 100 if d.get('f43') else 0
                iopv = d.get('f60', 0) / 100 if d.get('f60') else 0
                
                # 修正：如果IOPV远大于价格，可能数据有问题
                # 暂时不使用东方财富的IOPV
                return {
                    'price': price,
                    'iopv': None,  # 不使用
                    'change': d.get('f170', 0) / 100 if d.get('f170') else 0,
                }
        except:
            pass
        
        return None
    
    def monitor_all(self, threshold=1.5):
        """
        监控所有核心ETF
        threshold: 折溢价阈值(%)
        """
        print("=" * 80)
        print(f"跨境ETF折溢价监控 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        print(f"{'代码':<12} {'名称':<15} {'现价':<8} {'买一':<8} {'卖一':<8} {'净值':<8} {'溢价率':<8} {'信号'}")
        print("-" * 80)
        
        opportunities = []
        
        for etf_code, info in CORE_ETFS.items():
            # 获取ETF行情
            quote = self.get_etf_quote(etf_code)
            if not quote or quote['price'] == 0:
                continue
            
            # 计算实时净值
            realtime_nav, weighted_change = self.calculate_realtime_nav(etf_code, quote)
            
            # 如果没有权重数据，尝试东方财富
            if realtime_nav is None:
                em_data = self.get_etf_from_eastmoney(etf_code)
                if em_data and em_data.get('iopv') is not None and em_data['iopv'] > 0:
                    realtime_nav = em_data['iopv']
            
            # 计算溢价率
            if realtime_nav and realtime_nav > 0:
                premium = (quote['price'] - realtime_nav) / realtime_nav * 100
            else:
                premium = 0
                realtime_nav = quote['price']  # 无法计算，暂用现价
            
            # 判断信号
            signal = ""
            if abs(premium) >= threshold:
                if premium > 0:
                    signal = "🔴 溢价"
                else:
                    signal = "🟢 折价"
                opportunities.append({
                    'code': etf_code,
                    'name': info['name'],
                    'quote': quote,
                    'nav': realtime_nav,
                    'premium': premium,
                    'signal': signal
                })
            
            # 输出
            print(f"{etf_code:<12} {info['name']:<15} {quote['price']:<8.3f} "
                  f"{quote['bid1']:<8.3f} {quote['ask1']:<8.3f} "
                  f"{realtime_nav:<8.3f} {premium:+.2f}%     {signal}")
        
        print("-" * 80)
        
        # 输出套利机会
        if opportunities:
            print(f"\n发现 {len(opportunities)} 个套利机会：")
            print("=" * 80)
            for opp in opportunities:
                q = opp['quote']
                print(f"\n{opp['signal']} {opp['name']} ({opp['code']})")
                print(f"  现价: {q['price']:.3f} | 净值: {opp['nav']:.3f} | 溢价率: {opp['premium']:+.2f}%")
                print(f"  买一: {q['bid1']:.3f} × {q['bid1_vol']}手")
                print(f"  卖一: {q['ask1']:.3f} × {q['ask1_vol']}手")
                
                if opp['premium'] < 0:
                    print(f"  💡 操作: 买入ETF @ {q['ask1']:.3f}，对冲期货")
                else:
                    print(f"  💡 操作: 卖出ETF @ {q['bid1']:.3f}，买入期货对冲")
        else:
            print(f"\n未发现折溢价超过 {threshold}% 的套利机会")
        
        print("\n" + "=" * 80)
        return opportunities

def main():
    monitor = ETFArbMonitor()
    monitor.monitor_all(threshold=1.5)

if __name__ == "__main__":
    main()
