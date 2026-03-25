# AMS 技术可行性报告 - 股票数据源调研

> 版本: 1.0 | 日期: 2026-03-09 | 作者: Dev角色
> 
> 【调研目标】确定如何获取"前瞻估值"和"现金流数据"

---

## 1. 调研结论摘要

| 数据类型 | 推荐方案 | 可行性 | 成本 |
|----------|----------|--------|------|
| 财务报表（资产负债表、利润表、现金流量表） | AKShare | ✅ 完全可行 | 免费 |
| 财务指标（预计算） | AKShare / Tushare | ✅ 完全可行 | 免费/积分 |
| 前瞻PE / 盈利预测 | AKShare盈利预测-东财 | ✅ 可行 | 免费 |
| 分析师一致预期EPS | AKShare盈利预测-同花顺 | ✅ 可行 | 免费 |
| 实时股价 | AKShare实时行情 | ✅ 完全可行 | 免费 |

**总评**: 所需数据均可通过免费接口获取，技术可行性 **高**。

---

## 2. 数据源详细分析

### 2.1 AKShare（推荐首选）

#### 2.1.1 基本信息
- **官网**: https://akshare.akfamily.xyz
- **授权**: MIT开源协议
- **限制**: 无API调用限制
- **费用**: 完全免费

#### 2.1.2 财务数据接口

| 接口名称 | 功能 | 返回字段示例 |
|----------|------|-------------|
| `stock_financial_analysis_indicator` | 财务指标 | 营收增长率、净利润增长率等 |
| `stock_balance_sheet_by_report_em` | 资产负债表-东财 | 总资产、总负债、货币资金等 |
| `stock_profit_sheet_by_report_em` | 利润表-东财 | 营收、净利润等 |
| `stock_cash_flow_sheet_by_report_em` | 现金流量表-东财 | 经营活动现金流净额等 |

**示例代码**:
```python
import akshare as ak

# 获取资产负债表
balance_df = ak.stock_balance_sheet_by_report_em(symbol="000001")

# 获取现金流量表
cashflow_df = ak.stock_cash_flow_sheet_by_report_em(symbol="000001")

# 获取财务指标
indicator_df = ak.stock_financial_analysis_indicator(symbol="000001")
```

#### 2.1.3 盈利预测接口（前瞻PE核心）

| 接口名称 | 功能 | 数据来源 |
|----------|------|----------|
| `stock_profit_forecast_em` | 盈利预测-东方财富 | 东方财富网 |
| `stock_profit_forecast_ths` | 盈利预测-同花顺 | 同花顺iFinD |

**东方财富盈利预测返回字段**:
- 预测年份
- 预测EPS（分析师一致预期）
- 预测PE
- 预测净利润
- 分析师数量
- 预测机构列表

**示例代码**:
```python
import akshare as ak

# 获取盈利预测
forecast_df = ak.stock_profit_forecast_em(symbol="000001")

# 计算前瞻PE
current_price = 15.50  # 当前股价
forecast_eps = forecast_df['预测EPS'].iloc[0]  # 2026年预测EPS
forward_pe = current_price / forecast_eps
```

#### 2.1.4 行情数据接口

| 接口名称 | 功能 | 说明 |
|----------|------|------|
| `stock_zh_a_spot_em` | A股实时行情 | 东财数据，全市场 |
| `stock_individual_info_em` | 个股信息 | 包含PE、PB等 |

---

### 2.2 Tushare Pro（备用方案）

#### 2.2.1 基本信息
- **官网**: https://tushare.pro
- **授权**: 需注册获取Token
- **限制**: 按积分调用，每日有额度
- **费用**: 基础免费，高级功能需付费

#### 2.2.2 相关接口

| 接口名称 | 功能 | 积分要求 |
|----------|------|----------|
| `income` | 利润表 | 5000积分 |
| `balancesheet` | 资产负债表 | 5000积分 |
| `cashflow` | 现金流量表 | 5000积分 |
| `fina_indicator` | 财务指标 | 5000积分 |
| `stk_holdernumber` | 股东户数 | 免费积分 |

**注意**: Tushare的盈利预测接口需要较高积分，建议使用AKShare作为首选。

---

### 2.3 东方财富开放平台（补充方案）

#### 2.3.1 基本信息
- **官网**: https://open.eastmoney.com
- **授权**: 需申请API Key
- **限制**: 有调用频率限制
- **费用**: 部分免费

#### 2.3.2 可用数据
- 实时行情
- 财务数据
- 机构调研
- 盈利预测

---

## 3. 关键数据获取方案

### 3.1 前瞻PE获取流程

```python
def get_forward_pe(stock_code: str) -> dict:
    """
    获取前瞻PE
    流程:
    1. 获取当前股价
    2. 获取分析师一致预期EPS
    3. 计算前瞻PE = 股价 / 预期EPS
    """
    import akshare as ak
    
    # Step 1: 获取当前股价
    spot_df = ak.stock_zh_a_spot_em()
    current_price = spot_df[spot_df['代码'] == stock_code]['最新价'].values[0]
    
    # Step 2: 获取盈利预测
    forecast_df = ak.stock_profit_forecast_em(symbol=stock_code)
    
    # Step 3: 计算前瞻PE
    # 取2026年预测EPS
    eps_2026 = forecast_df[forecast_df['年份'] == 2026]['预测EPS'].values[0]
    forward_pe = current_price / eps_2026
    
    return {
        'stock_code': stock_code,
        'current_price': current_price,
        'forecast_eps_2026': eps_2026,
        'forward_pe': forward_pe,
        'analyst_count': len(forecast_df)
    }
```

### 3.2 现金流数据获取流程

```python
def get_cashflow_metrics(stock_code: str) -> dict:
    """
    获取现金流相关指标
    """
    import akshare as ak
    
    # 获取现金流量表
    cashflow_df = ak.stock_cash_flow_sheet_by_report_em(symbol=stock_code)
    
    # 获取利润表（用于计算现金流质量）
    profit_df = ak.stock_profit_sheet_by_report_em(symbol=stock_code)
    
    # 提取最新报告期数据
    latest_cashflow = cashflow_df.iloc[0]
    latest_profit = profit_df.iloc[0]
    
    # 计算现金流质量 = 经营现金流 / 净利润
    operating_cf = latest_cashflow['经营活动产生的现金流量净额']
    net_profit = latest_profit['净利润']
    cf_quality = operating_cf / net_profit if net_profit != 0 else 0
    
    return {
        'stock_code': stock_code,
        'operating_cashflow': operating_cf,
        'net_profit': net_profit,
        'cf_quality': cf_quality,
        'report_date': latest_cashflow['报告期']
    }
```

### 3.3 全量股票筛选流程

```python
def scan_all_stocks() -> list:
    """
    全量股票扫描筛选
    """
    import akshare as ak
    import pandas as pd
    
    # 1. 获取全市场股票列表
    stock_list = ak.stock_zh_a_spot_em()
    
    # 2. 遍历每只股票，获取财务数据
    results = []
    for idx, row in stock_list.head(100).iterrows():  # 测试取前100只
        try:
            stock_code = row['代码']
            
            # 获取财务指标
            indicator_df = ak.stock_financial_analysis_indicator(symbol=stock_code)
            
            # 获取盈利预测
            forecast_df = ak.stock_profit_forecast_em(symbol=stock_code)
            
            # 计算评分...
            
            results.append({
                'code': stock_code,
                'name': row['名称'],
                'price': row['最新价'],
                # ... 更多字段
            })
            
        except Exception as e:
            print(f"Error processing {stock_code}: {e}")
            continue
    
    return results
```

---

## 4. 技术风险评估

| 风险项 | 风险等级 | 缓解措施 |
|--------|----------|----------|
| 接口不稳定 | 中 | 多数据源备份，本地缓存 |
| 数据缺失 | 低 | 跳过该股票，不中断流程 |
| 调用频率限制 | 低 | AKShare无限制，Tushare有积分控制 |
| 数据延迟 | 低 | 财务数据T+1可接受 |
| 分析师预测偏差 | 中 | QA校验方案覆盖 |

---

## 5. 实施建议

### 5.1 开发优先级

1. **P0 - 核心功能**
   - 财务数据获取（AKShare）
   - 前瞻PE计算（盈利预测接口）
   - 基础评分算法

2. **P1 - 增强功能**
   - 多数据源备份
   - 本地数据缓存
   - 增量更新机制

3. **P2 - 优化功能**
   - 并行数据获取
   - 数据质量监控
   - 异常告警

### 5.2 技术栈建议

```python
# requirements.txt
akshare>=1.12.0
pandas>=2.0.0
numpy>=1.24.0
requests>=2.28.0
```

### 5.3 数据存储结构

```
AMS/
├── radar_data/
│   ├── stock_list.json       # 股票列表
│   ├── financial/            # 财务数据
│   │   ├── {code}_balance.json
│   │   ├── {code}_profit.json
│   │   └── {code}_cashflow.json
│   ├── forecast/             # 盈利预测
│   │   └── {code}_forecast.json
│   └── scores/               # 评分结果
│       └── {date}_scores.json
```

---

## 6. 结论

**技术可行性评估: ✅ 完全可行**

所有PRD定义的6个量化指标均可通过免费开源接口（AKShare）获取，无需额外付费。

**关键依赖**:
- AKShare财务报表接口：资产负债表、利润表、现金流量表
- AKShare盈利预测接口：前瞻PE计算的核心数据源
- AKShare实时行情接口：当前股价获取

**开发周期估算**:
- 数据层开发：2-3天
- 评分算法实现：1-2天
- 测试与优化：1-2天
- **总计：4-7天**

---

*文档结束 - AMS项目组 Dev角色*
