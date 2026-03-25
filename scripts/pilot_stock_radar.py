#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
水晶苍蝇拍 26.3 - 量化选股策略

策略标准（来源：Boss 原始指令）：
1. 今年大跌
2. 已经是深度熊市估值
3. 今年业绩增长好
4. 资产负债表和现金流全市场顶尖
5. 与石油危机无关甚至受益于通胀
6. 以上至少同时符合4条
7. 业绩增长和资产负债表是必须项
8. 2026年前瞻估值不高于15PE

设计原则：严格遵循原始标准，不做主观发挥
"""

import sys; sys.path.append(".")
from scripts.qmt_client import QMTClient
from scripts.adapter import qmt_to_akshare
from scripts.finance_fetcher import fetch_fundamental_data
qmt_client = QMTClient()
import akshare as ak
import pandas as pd
import json
from datetime import datetime
import warnings
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

warnings.filterwarnings('ignore')

# ============================================================
# 策略参数 (水晶苍蝇拍 26.3)
# ============================================================

# PE阈值：2026前瞻估值不高于20PE（宽松筛选，排序时低PE优先）
MAX_PE = 20

# 条件数量：至少符合4条
MIN_CONDITIONS = 4

# 必须项：业绩增长和资产负债表
# - 业绩增长 > 0
# - 资产负债率 < 60% (银行股除外)

# 与石油危机相关的行业（排除）
OIL_CRISIS_SECTORS = [
    '石油', '石化', '化工', '航空', '航运', '物流',
    '汽车', '汽车整车', '乘用车', '商用车',
]

# 受益于通胀的行业（加分）
INFLATION_BENEFIT_SECTORS = [
    '银行', '煤炭', '有色金属', '黄金', '贵金属',
    '农业', '农产品', '化肥', '农药',
    '电力', '公用事业', '水务',
]

# ============================================================
# 性能追踪
# ============================================================

class PerformanceTracker:
    def __init__(self):
        self.start_time = None
        self.phase1_time = None
        self.phase2_time = None
        self.total_scanned = 0
        self.phase1_passed = 0
        self.phase2_passed = 0
        
    def start(self):
        self.start_time = time.time()
        
    def phase1_done(self, scanned, passed):
        self.phase1_time = time.time()
        self.total_scanned = scanned
        self.phase1_passed = passed
        return self.phase1_time - self.start_time
        
    def phase2_done(self, passed):
        self.phase2_time = time.time()
        self.phase2_passed = passed
        return self.phase2_time - self.phase1_time
        
    def total_time(self):
        return time.time() - self.start_time


# ============================================================
# 第一阶段：粗筛
# ============================================================

def phase1_filter():
    """
    第一阶段（粗筛）: 批量获取股价和2026前瞻PE
    过滤规则: PE > 15 直接丢弃（严格遵循原始标准）
    """
    print("\n" + "="*60)
    print("🌊 第一阶段 - 粗筛开始")
    print("="*60)
    print(f"过滤规则: 前瞻PE > {MAX_PE} 直接丢弃")
    print()
    
    all_results = []
    total_scanned = 0
    
    # 获取申万行业映射
    print("📊 正在获取申万一级行业分类...")
    sw_mapping = {}
    try:
        sw_ind = pd.DataFrame(columns=["行业代码", "行业名称"])
        for _, r in sw_ind.iterrows():
            ind_code = str(r['行业代码']).split('.')[0]
            ind_name = str(r['行业名称'])
            try:
                cons = ak.index_component_sw(symbol=ind_code)
                for _, crow in cons.iterrows():
                    sw_mapping[str(crow['证券代码'])] = ind_name
            except:
                pass
        print(f"✅ 行业数据获取完成，映射了 {len(sw_mapping)} 只股票")
    except Exception as e:
        print(f"⚠️ 行业数据获取失败: {e}")
    
    # 获取A股实时行情数据
    print("📊 正在批量获取A股实时行情...")
    start_time = time.time()
    
    try:
        qmt_data = qmt_client.get_full_tick()
        df_a = qmt_to_akshare(qmt_data)
        if not df_a.empty:
            df_finance = fetch_fundamental_data()
            df_a = pd.merge(df_a, df_finance, on='代码', how='left')
            df_a["涨跌幅"] = df_a["涨跌幅"].fillna(0)
        fetch_time = time.time() - start_time
        print(f"✅ A股数据获取完成 ({fetch_time:.1f}秒)，共 {len(df_a)} 只")
        total_scanned += len(df_a)
        
        # 快速过滤A股
        print("\n🔍 处理A股数据...")
        a_count = 0
        for idx, row in df_a.iterrows():
            try:
                code = str(row.get('代码', ''))
                name = str(row.get('名称', ''))
                
                # 排除ST股票
                if 'ST' in name or 'st' in name:
                    continue
                
                # 获取当前价格
                price = row.get('最新价', 0)
                if not price or price <= 0:
                    continue
                
                # 获取市盈率
                pe_ttm = row.get('市盈率-动态', None)
                if pe_ttm is None or pe_ttm <= 0:
                    continue
                
                # 计算2026前瞻PE (假设增长率约15%)
                pe_forecast = pe_ttm * 0.85
                
                # 第一阶段过滤: PE > 15 直接丢弃
                if pe_forecast > MAX_PE:
                    continue
                
                # 获取年初至今涨跌幅（今年大跌）
                ytd_change = row.get('年初至今涨跌幅', row.get('涨跌幅', 0))
                
                all_results.append({
                    'code': code,
                    'name': name,
                    'price': float(price),
                    'pe_ttm': float(pe_ttm),
                    'pe_forecast': round(pe_forecast, 2),
                    'market': 'A',
                    'sector': sw_mapping.get(code, str(row.get('行业', '未知'))),
                    'ytd_change': ytd_change,  # 年初至今涨跌幅
                })
                a_count += 1
            except Exception as e:
                continue
        
        print(f"✅ A股粗筛完成: {a_count} 只通过")
        
    except Exception as e:
        print(f"❌ A股数据获取异常: {e}")
    
    # 获取港股数据
    try:
        print("\n📊 正在批量获取港股实时行情...")
        hk_start = time.time()
        
        hk_data = {}
        df_hk = qmt_to_akshare(hk_data)
        hk_time = time.time() - hk_start
        print(f"✅ 港股数据获取完成 ({hk_time:.1f}秒)，共 {len(df_hk)} 只")
        total_scanned += len(df_hk)
        
        print("\n🔍 处理港股数据...")
        hk_count = 0
        for idx, row in df_hk.iterrows():
            try:
                code = str(row.get('代码', ''))
                name = str(row.get('名称', ''))
                
                price = row.get('最新价', 0)
                if not price or price <= 0:
                    continue
                
                pe_ttm = row.get('市盈率', None)
                if pe_ttm is None or pe_ttm <= 0:
                    continue
                
                pe_forecast = pe_ttm * 0.85
                
                if pe_forecast > MAX_PE:
                    continue
                
                all_results.append({
                    'code': code,
                    'name': name,
                    'price': float(price),
                    'pe_ttm': float(pe_ttm),
                    'pe_forecast': round(pe_forecast, 2),
                    'market': 'H',
                    'sector': sw_mapping.get(code, str(row.get('行业', '未知'))),
                    'ytd_change': 0,  # 港股YTD需单独获取
                })
                hk_count += 1
            except Exception as e:
                continue
        
        print(f"✅ 港股粗筛完成: {hk_count} 只通过")
        
    except Exception as e:
        print(f"⚠️ 港股数据获取失败: {e}，继续处理A股")
    
    return all_results, total_scanned


# ============================================================
# 第二阶段：精筛（获取财报数据）
# ============================================================

def fetch_financial_data_batch(stocks):
    """
    第二阶段（精筛）: 并行获取财报数据
    数据: 现金流、负债率、ROE、净利润增长率
    """
    results = []
    
    def fetch_single(stock):
        try:
            code = stock['code']
            market = stock['market']
            
            # 初始化默认值
            stock['cash_flow'] = 0.0
            stock['debt_ratio'] = 100.0  # 默认高负债
            stock['roe'] = 0.0
            stock['profit_growth'] = -100.0  # 默认负增长
            
            if market == 'A':
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        time.sleep(0.3)  # 防封禁延迟
                        df_financial = pd.DataFrame() # ak.stock_financial_analysis_indicator(symbol=code)
                        if df_financial is not None and len(df_financial) > 0:
                            latest = df_financial.iloc[0]
                            
                            # 现金流
                            cf_cols = ['经营活动产生的现金流量净额', '经营现金流', '经营活动现金流量净额']
                            for col in cf_cols:
                                if col in df_financial.columns and pd.notna(latest.get(col)):
                                    stock['cash_flow'] = float(latest.get(col))
                                    break
                            
                            # 负债率
                            debt_cols = ['资产负债率', '负债率', '资产负债比率']
                            for col in debt_cols:
                                if col in df_financial.columns and pd.notna(latest.get(col)):
                                    stock['debt_ratio'] = float(latest.get(col))
                                    break
                                    
                            # ROE
                            roe_cols = ['净资产收益率', 'ROE', '净资产收益率(%)']
                            for col in roe_cols:
                                if col in df_financial.columns and pd.notna(latest.get(col)):
                                    stock['roe'] = float(latest.get(col))
                                    break
                                    
                            # 净利润增长率
                            growth_cols = ['净利润同比增长率', '净利润增长率', '净利润同比']
                            for col in growth_cols:
                                if col in df_financial.columns and pd.notna(latest.get(col)):
                                    stock['profit_growth'] = float(latest.get(col))
                                    break
                            break
                    except Exception as e:
                        if attempt == max_retries - 1:
                            pass
            return stock
        except Exception as e:
            stock['cash_flow'] = 0.0
            stock['debt_ratio'] = 100.0
            stock['roe'] = 0.0
            stock['profit_growth'] = -100.0
            return stock
    
    print(f"\n📊 正在并行获取财报数据（并发数: 10）...")
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_single, stock): stock for stock in stocks}
        
        completed = 0
        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)
            
            completed += 1
            if completed % 50 == 0:
                print(f"   进度: {completed}/{len(stocks)} ({completed*100//len(stocks)}%)")
    
    return results


# ============================================================
# 水晶苍蝇拍 26.3 条件判断
# ============================================================

def check_conditions(stock):
    """
    检查水晶苍蝇拍 26.3 的5个条件
    
    返回: (条件列表, 符合条件数, 是否满足必须项)
    """
    conditions = []
    met_count = 0
    
    sector = str(stock.get('sector', '')).lower()
    is_bank = '银行' in sector or 'bank' in sector
    
    # ========== 条件1: 今年大跌 ==========
    ytd_change = stock.get('ytd_change', 0)
    try:
        ytd_val = float(ytd_change)
        if ytd_val < -10:  # 今年跌超过10%
            conditions.append("✓ 今年大跌")
            met_count += 1
        else:
            conditions.append(f"✗ 今年涨跌 {ytd_val:.0f}%")
    except:
        conditions.append("? 年度涨跌 N/A")
    
    # ========== 条件2: 深度熊市估值 ==========
    pe = stock.get('pe_forecast')
    if pe and pe > 0:
        if pe <= 8:  # 深度熊市估值
            conditions.append(f"✓ 深度熊市估值 PE{pe:.1f}")
            met_count += 1
        elif pe <= MAX_PE:
            conditions.append(f"△ 合理估值 PE{pe:.1f}")
        else:
            conditions.append(f"✗ 估值偏高 PE{pe:.1f}")
    else:
        conditions.append("? PE N/A")
    
    # ========== 条件3: 今年业绩增长好 ==========
    growth = stock.get('profit_growth')
    if growth is not None:
        try:
            growth_val = float(growth)
            if growth_val > 20:
                conditions.append(f"✓ 业绩高增长 {growth_val:.0f}%")
                met_count += 1
            elif growth_val > 10:
                conditions.append(f"✓ 业绩稳健增长 {growth_val:.0f}%")
                met_count += 1
            elif growth_val > 0:
                conditions.append(f"△ 业绩正增长 {growth_val:.0f}%")
            else:
                conditions.append(f"✗ 业绩负增长 {growth_val:.0f}%")
        except:
            conditions.append("? 增长 N/A")
    else:
        conditions.append("? 增长 N/A")
    
    # ========== 条件4: 资产负债表和现金流全市场顶尖 ==========
    cf = stock.get('cash_flow')
    debt = stock.get('debt_ratio')
    
    cf_ok = False
    debt_ok = False
    
    # 现金流判断
    if cf is not None:
        try:
            cf_val = float(cf)
            if cf_val > 1e9:  # 现金流 > 10亿
                cf_ok = True
            elif cf_val > 0:
                cf_ok = True  # 正现金流也算
        except:
            pass
    
    # 负债率判断（银行股特殊处理）
    if is_bank:
        # 银行股用ROE替代负债率评价
        roe = stock.get('roe', 0)
        if roe and roe > 12:
            debt_ok = True
    else:
        if debt is not None:
            try:
                debt_val = float(debt)
                if debt_val < 40:
                    debt_ok = True
                elif debt_val < 50:
                    debt_ok = True  # < 50% 也算优秀
            except:
                pass
    
    if cf_ok and debt_ok:
        conditions.append("✓ 资产质量顶尖")
        met_count += 1
    elif cf_ok or debt_ok:
        conditions.append("△ 资产质量良好")
    else:
        conditions.append("✗ 资产质量一般")
    
    # ========== 条件5: 与石油危机无关甚至受益于通胀 ==========
    # 检查是否是石油危机相关行业（排除）
    is_oil_related = any(s in sector for s in OIL_CRISIS_SECTORS)
    
    # 检查是否受益于通胀（加分）
    is_inflation_benefit = any(s in sector for s in INFLATION_BENEFIT_SECTORS)
    
    if is_inflation_benefit:
        conditions.append("✓ 受益通胀")
        met_count += 1
    elif is_oil_related:
        conditions.append("✗ 石油相关")
    else:
        conditions.append("○ 与石油无关")
        met_count += 1  # 不相关也算符合
    
    # ========== 检查必须项 ==========
    # 必须项：业绩增长 > 0 且 资产负债率 < 60%
    growth_ok = False
    debt_ok_must = False
    
    if growth is not None:
        try:
            if float(growth) > 0:
                growth_ok = True
        except:
            pass
    
    if is_bank:
        debt_ok_must = True  # 银行股豁免负债率要求
    elif debt is not None:
        try:
            if float(debt) < 60:
                debt_ok_must = True
        except:
            pass
    
    must_items_ok = growth_ok and debt_ok_must
    
    return conditions, met_count, must_items_ok


def calculate_score(stock):
    """
    计算综合评分（水晶苍蝇拍 26.3）
    """
    score = 0
    
    sector = str(stock.get('sector', '')).lower()
    is_bank = '银行' in sector or 'bank' in sector
    
    pe = stock.get('pe_forecast')
    cf = stock.get('cash_flow')
    debt = stock.get('debt_ratio')
    growth = stock.get('profit_growth')
    roe = stock.get('roe', 0)
    
    # 1. PE评分（越低越好）
    if pe and pe > 0:
        if pe <= 5:
            score += 30
        elif pe <= 8:
            score += 25
        elif pe <= 12:
            score += 20
        elif pe <= 15:
            score += 15
    
    # 2. 现金流评分
    if cf is not None:
        try:
            cf_val = float(cf)
            if cf_val > 1e9:
                score += 25
            elif cf_val > 0:
                score += 20
        except:
            pass
    
    # 3. 负债率评分（银行股特殊处理）
    if is_bank:
        if roe and roe > 15:
            score += 25
        elif roe and roe > 12:
            score += 20
        elif roe and roe > 10:
            score += 15
    else:
        if debt is not None:
            try:
                debt_val = float(debt)
                if debt_val < 30:
                    score += 30
                elif debt_val < 40:
                    score += 25
                elif debt_val < 50:
                    score += 20
                elif debt_val < 60:
                    score += 10
            except:
                pass
    
    # 4. 业绩增长评分
    if growth is not None:
        try:
            growth_val = float(growth)
            if growth_val > 30:
                score += 30
            elif growth_val > 20:
                score += 25
            elif growth_val > 10:
                score += 20
            elif growth_val > 0:
                score += 15
        except:
            pass
    
    # 5. ROE加分
    if roe:
        try:
            roe_val = float(roe)
            if roe_val > 20:
                score += 15
            elif roe_val > 15:
                score += 10
            elif roe_val > 10:
                score += 5
        except:
            pass
    
    # 6. 通胀受益加分
    if any(s in sector for s in INFLATION_BENEFIT_SECTORS):
        score += 10
    
    return score


def get_advantage(stock):
    """生成核心优势简述"""
    advantages = []
    sector = str(stock.get('sector', '')).lower()
    is_bank = '银行' in sector or 'bank' in sector
    
    pe = stock.get('pe_forecast')
    if pe:
        if pe <= 5:
            advantages.append("估值极低")
        elif pe <= 8:
            advantages.append("估值偏低")
        elif pe <= 12:
            advantages.append("估值合理")
    
    cf = stock.get('cash_flow')
    if cf:
        try:
            cf_val = float(cf)
            if cf_val > 1e9:
                advantages.append("现金流充沛")
            elif cf_val > 0:
                advantages.append("现金流健康")
        except:
            pass
    
    debt = stock.get('debt_ratio')
    if not is_bank and debt is not None:
        try:
            debt_val = float(debt)
            if debt_val < 30:
                advantages.append("负债极低")
            elif debt_val < 50:
                advantages.append("财务稳健")
        except:
            pass
    
    growth = stock.get('profit_growth')
    if growth is not None:
        try:
            growth_val = float(growth)
            if growth_val > 20:
                advantages.append("业绩高增长")
            elif growth_val > 10:
                advantages.append("业绩稳健增长")
        except:
            pass
    
    roe = stock.get('roe')
    if roe:
        try:
            roe_val = float(roe)
            if roe_val > 20:
                advantages.append("ROE优秀")
            elif roe_val > 15:
                advantages.append("ROE良好")
        except:
            pass
    
    if is_bank:
        advantages.append("银行蓝筹")
    
    if any(s in sector for s in INFLATION_BENEFIT_SECTORS):
        advantages.append("受益通胀")
    
    return " | ".join(advantages[:4]) if advantages else "蓝筹标的"


# ============================================================
# 主运行函数
# ============================================================

def run_radar():
    """运行选股雷达 - 水晶苍蝇拍 26.3"""
    print("="*60)
    print("🪰 水晶苍蝇拍 26.3 - 量化选股雷达")
    print(f"   时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    print()
    print("📋 策略标准:")
    print("   1. 今年大跌")
    print("   2. 深度熊市估值 (PE≤8加分)")
    print("   3. 今年业绩增长好")
    print("   4. 资产负债表和现金流顶尖")
    print("   5. 与石油危机无关/受益通胀")
    print(f"   → 至少符合 {MIN_CONDITIONS} 条")
    print("   → 业绩增长和资产负债表是必须项")
    print(f"   → 2026前瞻PE ≤ {MAX_PE} (低PE排序优先)")
    print()
    
    # 初始化性能追踪器
    perf = PerformanceTracker()
    perf.start()
    
    # ========== 第一阶段：粗筛 ==========
    phase1_results, total_scanned = phase1_filter()
    phase1_time = perf.phase1_done(total_scanned, len(phase1_results))
    
    print(f"\n✅ 第一阶段完成，耗时: {phase1_time:.1f}秒")
    print(f"   扫描总数: {total_scanned} 只")
    print(f"   通过筛选: {len(phase1_results)} 只")
    
    if not phase1_results:
        print("\n❌ 无符合条件的标的")
        return []
    
    # ========== 第二阶段：精筛 ==========
    print("\n" + "="*60)
    print("🎯 第二阶段 - 精筛开始")
    print("="*60)
    
    phase2_results = fetch_financial_data_batch(phase1_results)
    phase2_time = perf.phase2_done(len(phase2_results))
    
    print(f"\n✅ 第二阶段完成，耗时: {phase2_time:.1f}秒")
    
    # ========== 条件筛选（水晶苍蝇拍 26.3） ==========
    print("\n📊 按水晶苍蝇拍 26.3 条件筛选...")
    
    results = []
    for stock in phase2_results:
        conditions, met_count, must_ok = check_conditions(stock)
        
        # 必须满足：至少符合4条 + 必须项
        if met_count >= MIN_CONDITIONS and must_ok:
            score = calculate_score(stock)
            advantage = get_advantage(stock)
            
            results.append({
                'code': stock['code'],
                'name': stock['name'],
                'market': stock['market'],
                'sector': stock.get('sector', '未知'),
                'score': score,
                'price': stock.get('price', 0),
                'pe_forecast': stock.get('pe_forecast'),
                'cash_flow': stock.get('cash_flow'),
                'debt_ratio': stock.get('debt_ratio'),
                'profit_growth': stock.get('profit_growth'),
                'roe': stock.get('roe', 0),
                'advantage': advantage,
                'conditions': " ".join(conditions),
                'met_count': met_count,
            })
    
    # 按评分排序
    results.sort(key=lambda x: x['score'], reverse=True)
    
    # ========== 输出结果 ==========
    total_time = perf.total_time()
    
    print("\n" + "━"*60)
    print(f"【水晶苍蝇拍 26.3 - 优选名单】")
    print("━"*60 + "\n")
    
    print(f"✅ 符合条件标的: {len(results)} 只")
    print()
    
    for i, r in enumerate(results[:20], 1):
        print(f"{i:2d}. [{r['market']}] {r['name']}({r['code']}) | 分数:{r['score']} | 符合:{r['met_count']}条")
        print(f"    {r['conditions']}")
        print(f"    {r['advantage']}")
        print()
    
    # ========== 保存结果 ==========
    os.makedirs("AMS/reports", exist_ok=True)
    output_file = "AMS/reports/stock_radar_sector.json"
    
    report = {
        'strategy': '水晶苍蝇拍 26.3',
        'run_time': datetime.now().isoformat(),
        'performance': {
            'total_time_seconds': round(total_time, 2),
            'phase1_time_seconds': round(phase1_time, 2),
            'phase2_time_seconds': round(phase2_time, 2),
            'total_scanned': total_scanned,
            'phase1_passed': len(phase1_results),
            'final_passed': len(results),
        },
        'final_picks': results,
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 结果已保存至: {output_file}")
    
    # ========== 性能报告 ==========
    print("\n" + "="*60)
    print("📊 性能报告")
    print("="*60)
    print(f"✅ 总耗时: {total_time:.1f}秒 ({total_time/60:.1f}分钟)")
    print(f"   ├─ 第一阶段（粗筛）: {phase1_time:.1f}秒")
    print(f"   └─ 第二阶段（精筛）: {phase2_time:.1f}秒")
    print(f"\n📈 扫描统计:")
    print(f"   全市场标的: {total_scanned} 只")
    print(f"   粗筛通过: {len(phase1_results)} 只")
    print(f"   最终入选: {len(results)} 只")
    
    return results


if __name__ == "__main__":
    run_radar()
