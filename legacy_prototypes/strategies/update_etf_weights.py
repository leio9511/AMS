#!/usr/bin/env python3
"""
ETF成分股权重数据获取工具
从基金公司公告/第三方数据源获取最新权重
"""

import requests
import re
import json
from datetime import datetime
from pathlib import Path

def get_etf_holdings_from_eastmoney(etf_code):
    """
    从东方财富获取ETF持仓数据
    etf_code: ETF代码（如 513050）
    返回：成分股列表
    """
    # 转换代码格式
    if etf_code.startswith('sh'):
        fund_code = etf_code[2:]
    elif etf_code.startswith('sz'):
        fund_code = etf_code[2:]
    else:
        fund_code = etf_code
    
    print(f"获取 {fund_code} 的持仓数据...")
    
    # 东方财富基金持仓接口
    url = "http://fundf10.eastmoney.com/FundArchivesDatas.aspx"
    params = {
        "type": "jjcc",
        "code": fund_code,
        "topline": "10",
        "year": "2024",
        "month": "12"  # 最新季度
    }
    
    try:
        resp = requests.get(url, params=params, timeout=10)
        content = resp.text
        
        # 解析HTML
        # 提取股票代码、名称、持仓占比
        pattern = r'<td>(\d+)</td>.*?<td>(.*?)</td>.*?<td.*?>(\d+\.\d+)</td>'
        matches = re.findall(pattern, content, re.DOTALL)
        
        if matches:
            print(f"  找到 {len(matches)} 个持仓")
            for match in matches[:10]:
                seq, name, ratio = match
                print(f"    {seq}. {name} - {ratio}%")
        
        return matches
        
    except Exception as e:
        print(f"  获取失败: {e}")
        return None

def get_etf_info_from_eastmoney(etf_code):
    """
    获取ETF基本信息
    """
    if etf_code.startswith('sh'):
        fund_code = etf_code[2:]
    elif etf_code.startswith('sz'):
        fund_code = etf_code[2:]
    else:
        fund_code = etf_code
    
    url = "http://fundgz.1234567.com.cn/js/" + fund_code + ".js"
    
    try:
        resp = requests.get(url, timeout=5)
        content = resp.text
        
        # 解析 jsonpgz({...})
        match = re.search(r'jsonpgz\((.*)\)', content)
        if match:
            data = json.loads(match.group(1))
            return {
                'code': data.get('fundcode'),
                'name': data.get('name'),
                'nav': data.get('dwjz'),  # 单位净值
                'date': data.get('jzrq'),  # 净值日期
            }
    except:
        pass
    
    return None

def update_etf_weights(etf_code, manual_weights=None):
    """
    更新ETF权重数据
    manual_weights: 手动提供的权重数据
    """
    weight_file = Path(__file__).parent / "etf_weights.json"
    
    # 加载现有数据
    if weight_file.exists():
        with open(weight_file, 'r', encoding='utf-8') as f:
            all_weights = json.load(f)
    else:
        all_weights = {}
    
    # 更新数据
    if manual_weights:
        all_weights[etf_code] = {
            'weights': manual_weights,
            'update_time': datetime.now().isoformat()
        }
        
        # 保存
        with open(weight_file, 'w', encoding='utf-8') as f:
            json.dump(all_weights, f, ensure_ascii=False, indent=2)
        
        print(f"已更新 {etf_code} 的权重数据")
    
    return all_weights

def main():
    print("=" * 60)
    print("ETF权重数据管理工具")
    print("=" * 60)
    
    print("\n现有权重数据：")
    print("-" * 60)
    
    from cross_border_etf_monitor import ETF_WEIGHTS
    
    for etf_code, weights in ETF_WEIGHTS.items():
        print(f"\n{etf_code}:")
        for stock_code, info in list(weights.items())[:5]:
            print(f"  {stock_code} - {info['name']}: {info['weight']}%")
        if len(weights) > 5:
            print(f"  ... (共{len(weights)}个成分股)")
    
    print("\n" + "=" * 60)
    print("如何添加新的ETF权重数据：")
    print("=" * 60)
    print("""
1. 查看基金季报：
   - 访问基金公司官网或第三方基金网站
   - 找到ETF的最新持仓公告
   - 记录前十大持仓股票代码和权重

2. 手动添加权重：
   编辑 strategies/cross_border_etf_monitor.py
   在 ETF_WEIGHTS 字典中添加：
   
   "sh513xxx": {
       "hk00700": {"name": "腾讯控股", "weight": 10.5},
       "hk09988": {"name": "阿里巴巴", "weight": 8.2},
       ...
   },

3. 注意事项：
   - 港股代码格式：hk00700, hk09988
   - 美股代码格式：usAAPL, usMSFT
   - 权重单位：百分比（如 10.5 表示 10.5%）
   - 建议每季度更新一次
    """)

if __name__ == "__main__":
    main()
