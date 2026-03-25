# M2: ETF 监控增强 - 真实性判断

## 📊 状态

| 阶段 | 状态 |
|------|------|
| PM PRD | ✅ 已完成 |
| TL 方案 | ✅ 已完成 |
| QA 标准 | ✅ 已完成 |
| 团队对齐 | ✅ 已确认 |
| 执行 | ✅ 已完成 |
| 验收 | ✅ 已完成 |

---

## 📋 PRD (PM)

**完整 PRD**: `AMS/MILESTONES/AMS_PRD_v5.1.md` (模块一)

### 功能需求

| ID | 需求 | 优先级 | 说明 |
|----|------|--------|------|
| FR-1 | 美股隔夜数据获取 | P0 | 纳指/标普/道指涨跌幅 (已有) |
| FR-2 | 港股实时数据获取 | P0 | 恒生科技/恒生指数 (新增) |
| FR-3 | 真实性判断优化 | P0 | 区分真假折价机会 |
| FR-4 | QDII 额度查询 | P2 | 申购通道状态 (后续) |

### 当前完成度

| 功能 | 状态 | 说明 |
|------|------|------|
| 美股数据获取 | ✅ 已有 | fetch_us_index_data() |
| 真实性判断 | 🔵 部分 | 仅支持美股ETF |
| 港股数据获取 | ❌ 缺失 | 需要新增 |
| 港股判断逻辑 | ❌ 缺失 | 需要新增 |

### 验收标准

| ID | 标准 | 验收方式 |
|----|------|----------|
| AC-1 | 美股ETF折价时显示隔夜走势 | 消息内容 |
| AC-2 | 港股ETF折价时显示实时走势 | 消息内容 |
| AC-3 | 判断结论明确 | 消息包含"真实机会"/"虚假机会" |

---

## 🔧 技术方案 (TL)

### 1. 港股数据获取

```python
HK_INDEX_CODES = {
    'hsi': 'hkHSI',      # 恒生指数
    'hstech': 'hkHSTECH' # 恒生科技
}

def fetch_hk_index_data():
    """获取港股指数实时数据"""
    results = {}
    for name, code in HK_INDEX_CODES.items():
        try:
            url = f"http://qt.gtimg.cn/q={code}"
            r = requests.get(url, timeout=5)
            r.encoding = 'gbk'
            if '~' in r.text:
                fields = r.text.split('~')
                change_pct = to_float(fields[3]) if len(fields) > 3 else 0
                results[name] = {'change_pct': change_pct}
        except: pass
    return results
```

### 2. 真实性判断逻辑增强

```python
def get_reasoning(code, diff, us_data=None, hk_data=None):
    """智能分析: 判断折溢价真实性"""
    
    # 美股 ETF 判断
    if code in STALE_NAV_CODES and diff < -0.003:
        nasdaq = us_data.get('nasdaq', {}).get('change_pct', 0) if us_data else 0
        if nasdaq < -1:
            return f"\n🧐 分析: 折价反映隔夜美股下跌(纳指{nasdaq:.2f}%)，❌虚假机会，观望"
        elif nasdaq > 0.5:
            return f"\n🧐 分析: 美股隔夜上涨(纳指+{nasdaq:.2f}%)，✅可能是真实机会，关注申购通道"
        else:
            return f"\n🧐 分析: 时滞风险，等待净值更新后重新评估"
    
    # 港股 ETF 判断
    if code in ['sh513330', 'sh513050'] and diff < -0.003:
        hstech = hk_data.get('hstech', {}).get('change_pct', 0) if hk_data else 0
        if hstech < -1:
            return f"\n🧐 分析: 折价反映港股下跌(恒科{hstech:.2f}%)，❌虚假机会，观望"
        elif hstech > 0:
            return f"\n🧐 分析: 港股上涨中(恒科+{hstech:.2f}%)，✅可能是真实机会"
        else:
            return f"\n🧐 分析: 港股横盘，需进一步观察"
    
    # 溢价判断
    if diff > 0.01:
        return f"\n🧐 分析: 溢价极高，确认 QDII 申购通道状态"
    
    return ""
```

### 3. 文件变更

| 文件 | 变更 |
|------|------|
| `etf_tracker.py` | 新增港股数据获取 + 优化判断逻辑 |

---

## ✅ 测试方案 (QA)

### 自动化测试

| Test ID | 测试项 | 预期结果 |
|---------|--------|----------|
| M2-T1 | 美股数据获取 | 返回纳指/标普涨跌幅 |
| M2-T2 | 港股数据获取 | 返回恒生科技涨跌幅 |
| M2-T3 | 美股ETF判断 | 折价时显示隔夜走势 |
| M2-T4 | 港股ETF判断 | 折价时显示实时走势 |
| M2-T5 | 结论明确 | 包含"✅"或"❌"标识 |

### 手动验收

| 步骤 | 操作 | 预期 |
|------|------|------|
| 1 | 触发测试报告 | 消息包含分析内容 |
| 2 | 检查港股ETF分析 | 显示恒生科技走势 |

---

## 📝 Sprint Log

| 时间 | 事件 | Git Hash |
|------|------|----------|
| 2026-03-10 19:45 | M2 SDLC 启动 | - |
| 2026-03-10 19:47 | PM/TL/QA 对齐完成 | 待提交 |

---

*创建时间: 2026-03-10 19:45 (UTC+8)*
*最后更新: 2026-03-10 19:47 (UTC+8)*
