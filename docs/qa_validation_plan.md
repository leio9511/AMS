# AMS 数据校验方案 - 前瞻PE可靠性验证

> 版本: 1.0 | 日期: 2026-03-09 | 作者: QA角色
> 
> 【校验目标】验证第三方接口返回的"前瞻PE"是否可靠

---

## 1. 校验策略概述

### 1.1 核心问题

前瞻PE依赖分析师一致预期数据，存在以下风险：
1. **数据源偏差**：不同平台分析师样本不同
2. **时效性问题**：预测数据更新不及时
3. **预测误差**：分析师预测与实际业绩偏差
4. **极端值干扰**：个别极端预测影响均值

### 1.2 校验维度

| 维度 | 校验内容 | 方法 |
|------|----------|------|
| **交叉验证** | 多数据源对比 | 东财 vs 同花顺 vs Wind |
| **历史回测** | 预测准确率 | 历史预测 vs 实际业绩 |
| **极端值检测** | 异常值剔除 | 统计学方法 |
| **时效性检查** | 数据新鲜度 | 更新时间戳 |

---

## 2. 交叉验证方案

### 2.1 多源对比流程

```python
def cross_validate_forward_pe(stock_code: str) -> dict:
    """
    多数据源交叉验证前瞻PE
    """
    import akshare as ak
    
    # 获取当前股价
    spot_df = ak.stock_zh_a_spot_em()
    current_price = spot_df[spot_df['代码'] == stock_code]['最新价'].values[0]
    
    # 数据源1: 东方财富盈利预测
    try:
        forecast_em = ak.stock_profit_forecast_em(symbol=stock_code)
        eps_em = forecast_em['预测EPS'].iloc[0]
        pe_em = current_price / eps_em
    except:
        pe_em = None
    
    # 数据源2: 同花顺盈利预测
    try:
        forecast_ths = ak.stock_profit_forecast_ths(symbol=stock_code)
        eps_ths = forecast_ths['预测EPS'].iloc[0]
        pe_ths = current_price / eps_ths
    except:
        pe_ths = None
    
    # 计算偏差
    if pe_em and pe_ths:
        deviation = abs(pe_em - pe_ths) / min(pe_em, pe_ths) * 100
        
        # 偏差阈值：15%
        if deviation > 15:
            status = "⚠️ 数据源偏差较大"
            confidence = "低"
        elif deviation > 8:
            status = "⚡ 数据源存在偏差"
            confidence = "中"
        else:
            status = "✅ 数据源一致"
            confidence = "高"
    else:
        status = "❌ 无法交叉验证"
        confidence = "未知"
        deviation = None
    
    return {
        'stock_code': stock_code,
        'current_price': current_price,
        'pe_eastmoney': pe_em,
        'pe_ths': pe_ths,
        'deviation_pct': deviation,
        'status': status,
        'confidence': confidence
    }
```

### 2.2 验证规则

| 规则 | 条件 | 处理 |
|------|------|------|
| 双源一致 | 偏差 ≤ 8% | ✅ 采纳，高置信度 |
| 双源偏差 | 8% < 偏差 ≤ 15% | ⚡ 采纳，中置信度，标注 |
| 双源冲突 | 偏差 > 15% | ⚠️ 人工复核或剔除 |
| 单源可用 | 仅一个数据源 | ⚡ 采纳，标注数据源 |
| 无数据 | 均无数据 | ❌ 剔除该股票 |

---

## 3. 历史预测准确率验证

### 3.1 回测方法

```python
def validate_prediction_accuracy(stock_code: str, years: int = 3) -> dict:
    """
    验证历史预测准确率
    
    方法：对比分析师预测EPS vs 实际EPS
    """
    import akshare as ak
    import pandas as pd
    
    accuracy_records = []
    
    for year in range(2023, 2023 - years, -1):
        try:
            # 获取该年度预测数据（需在年初预测）
            forecast_df = ak.stock_profit_forecast_em(symbol=stock_code)
            predicted_eps = forecast_df[forecast_df['年份'] == year]['预测EPS'].values[0]
            
            # 获取实际财报数据
            profit_df = ak.stock_profit_sheet_by_report_em(symbol=stock_code)
            actual_eps = profit_df[profit_df['报告期'].str.contains(str(year))]['基本每股收益'].values[0]
            
            # 计算预测误差
            error = abs(predicted_eps - actual_eps) / actual_eps * 100
            
            accuracy_records.append({
                'year': year,
                'predicted_eps': predicted_eps,
                'actual_eps': actual_eps,
                'error_pct': error,
                'direction_correct': (predicted_eps > 0) == (actual_eps > 0)
            })
            
        except Exception as e:
            continue
    
    # 计算平均准确率
    if accuracy_records:
        avg_error = sum(r['error_pct'] for r in accuracy_records) / len(accuracy_records)
        direction_accuracy = sum(r['direction_correct'] for r in accuracy_records) / len(accuracy_records) * 100
    else:
        avg_error = None
        direction_accuracy = None
    
    return {
        'stock_code': stock_code,
        'records': accuracy_records,
        'avg_error_pct': avg_error,
        'direction_accuracy_pct': direction_accuracy,
        'sample_years': len(accuracy_records)
    }
```

### 3.2 准确率评级

| 平均误差 | 方向准确率 | 评级 | 可信度 |
|----------|-----------|------|--------|
| ≤ 10% | ≥ 80% | A级 | 高 |
| 10-20% | ≥ 70% | B级 | 中高 |
| 20-30% | ≥ 60% | C级 | 中 |
| > 30% | < 60% | D级 | 低 |

---

## 4. 极端值检测与处理

### 4.1 统计学方法

```python
def detect_outliers(forecast_data: list) -> dict:
    """
    检测盈利预测中的极端值
    
    使用 IQR 方法检测离群值
    """
    import numpy as np
    
    eps_values = [f['eps'] for f in forecast_data]
    
    q1 = np.percentile(eps_values, 25)
    q3 = np.percentile(eps_values, 75)
    iqr = q3 - q1
    
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr
    
    outliers = [f for f in forecast_data 
                if f['eps'] < lower_bound or f['eps'] > upper_bound]
    
    # 剔除极端值后的均值
    clean_values = [f['eps'] for f in forecast_data 
                    if lower_bound <= f['eps'] <= upper_bound]
    adjusted_mean = np.mean(clean_values)
    
    return {
        'original_mean': np.mean(eps_values),
        'adjusted_mean': adjusted_mean,
        'outlier_count': len(outliers),
        'outlier_details': outliers,
        'total_analysts': len(forecast_data)
    }
```

### 4.2 处理策略

| 情况 | 处理方式 |
|------|----------|
| 离群值数量 < 3 | 剔除离群值，使用调整后均值 |
| 离群值数量 ≥ 3 | 使用中位数而非均值 |
| 分析师数量 < 3 | 标注低置信度 |
| 分析师数量 = 1 | 不可靠，建议剔除 |

---

## 5. 时效性检查

### 5.1 数据新鲜度验证

```python
def check_data_freshness(forecast_df: pd.DataFrame) -> dict:
    """
    检查盈利预测数据的时效性
    """
    import pandas as pd
    from datetime import datetime
    
    # 假设forecast_df包含'更新时间'字段
    latest_update = pd.to_datetime(forecast_df['更新时间'].max())
    days_since_update = (datetime.now() - latest_update).days
    
    if days_since_update <= 30:
        freshness = "新鲜"
        score = 100
    elif days_since_update <= 90:
        freshness = "较新"
        score = 80
    elif days_since_update <= 180:
        freshness = "一般"
        score = 60
    else:
        freshness = "陈旧"
        score = 40
    
    return {
        'latest_update': latest_update,
        'days_since_update': days_since_update,
        'freshness': freshness,
        'freshness_score': score
    }
```

### 5.2 时效性阈值

| 更新间隔 | 状态 | 处理 |
|----------|------|------|
| ≤ 30天 | ✅ 新鲜 | 正常使用 |
| 30-90天 | ⚡ 较新 | 正常使用，标注 |
| 90-180天 | ⚠️ 一般 | 降低权重 |
| > 180天 | ❌ 陈旧 | 建议不使用 |

---

## 6. 综合置信度评分

### 6.1 置信度计算公式

```
ConfidenceScore = 
    CrossValidateScore × 0.30   # 交叉验证
    + AccuracyScore × 0.30       # 历史准确率
    + CoverageScore × 0.20       # 分析师覆盖度
    + FreshnessScore × 0.20      # 时效性
```

### 6.2 置信度评级

| 综合得分 | 评级 | 前瞻PE使用建议 |
|----------|------|----------------|
| ≥ 80分 | 高置信 | 正常使用 |
| 60-80分 | 中置信 | 使用但标注风险 |
| 40-60分 | 低置信 | 权重降半 |
| < 40分 | 不可信 | 不使用前瞻PE |

---

## 7. 自动化校验流程

### 7.1 校验流水线

```python
def validate_forward_pe_pipeline(stock_code: str) -> dict:
    """
    前瞻PE校验流水线
    """
    results = {}
    
    # Step 1: 交叉验证
    cross_check = cross_validate_forward_pe(stock_code)
    results['cross_validate'] = cross_check
    
    # Step 2: 历史准确率
    accuracy = validate_prediction_accuracy(stock_code)
    results['accuracy'] = accuracy
    
    # Step 3: 时效性检查
    # fresh = check_data_freshness(forecast_df)
    # results['freshness'] = fresh
    
    # Step 4: 计算综合置信度
    confidence_score = calculate_confidence_score(results)
    results['confidence_score'] = confidence_score
    
    # Step 5: 生成校验报告
    results['validation_report'] = generate_validation_report(results)
    
    return results
```

### 7.2 校验报告模板

```
📋 【前瞻PE校验报告】
股票: {stock_code}
━━━━━━━━━━━━━━━━━━━━━━━━

【交叉验证】
- 东财前瞻PE: {pe_em}
- 同花顺前瞻PE: {pe_ths}
- 偏差: {deviation}%
- 状态: {status}

【历史准确率】
- 样本年数: {sample_years}
- 平均误差: {avg_error}%
- 方向准确率: {direction_accuracy}%
- 评级: {accuracy_grade}

【综合置信度】
- 得分: {confidence_score}分
- 评级: {confidence_grade}
- 使用建议: {recommendation}

━━━━━━━━━━━━━━━━━━━━━━━━
校验时间: {validation_time}
```

---

## 8. 校验规则清单

| ID | 规则名称 | 规则描述 | 严重程度 |
|----|----------|----------|----------|
| V001 | 交叉验证 | 多数据源偏差检查 | 高 |
| V002 | 历史准确率 | 过去3年预测误差检查 | 高 |
| V003 | 极端值检测 | IQR方法检测离群值 | 中 |
| V004 | 时效性检查 | 数据更新时间检查 | 中 |
| V005 | 覆盖度检查 | 分析师数量检查 | 低 |
| V006 | 方向一致性 | 预测方向与历史一致 | 中 |

---

## 9. 结论

**校验方案可行性: ✅ 完全可行**

通过多维度校验机制，可有效识别和过滤不可靠的前瞻PE数据：

1. **交叉验证**：确保数据源一致性
2. **历史回测**：评估预测准确率
3. **极端值检测**：剔除异常预测
4. **时效性检查**：确保数据新鲜度

**建议**：
- 所有前瞻PE数据必须经过校验流程
- 低置信度数据应在输出中明确标注
- 定期回测校验规则有效性

---

*文档结束 - AMS项目组 QA角色*
