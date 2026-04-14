---
Affected_Projects: [AMS]
---

# PRD: MiniQMT_Event_Driven_Execution

## 1. Context & Problem (业务背景与核心痛点)
经过完整的历史仿真回测，AMS 系统已验证了“周频/日频双低轮动 + 5%盘中脉冲止盈”策略的超额收益能力。为进入模拟盘/实盘部署阶段，需要将模型生成的“理论交易信号”转化为券商柜台的真实委托。
当前采用 MiniQMT 作为交易网关。为避免直接挂单导致的“持仓冻结”以及轮询 (`while True`) 导致的“CPU 爆满”，必须采用“事件驱动 (Event-Driven)”的架构来实现无头值守交易。

## 2. Requirements & User Stories (需求定义)
- **底仓轮动同步**：系统每日读取 `target_positions.json`，查询当前 QMT 持仓，计算出差异（State Diff），并对多出的转债发市价卖出委托，对缺少的转债发市价买入委托。
- **暗盘止盈监控**：系统盘中对所有持仓转债通过底层 C++ 事件回调（`subscribe_quote`）进行 Tick 级监控。当触发目标止盈价（默认 1.05 * 成本价）时，系统自动发送极速市价卖出指令，落袋为安。
- **高并发防重复发单（幂等性保护）**：在极端的毫秒级连续高频 Tick 触发下，同一只标的只能触发一次止盈下单操作，直到收到明确的废单或成交回调状态。

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- 新建模块 `projects/AMS/windows_bridge/qmt_trader_sync.py`。
- **核心组件 1：XtQuantTrader 初始化与回调挂载**：启动 `XtQuantTrader`，挂载继承自 `XtQuantTraderCallback` 的回调类，处理断线重连、委托状态推送。
- **核心组件 2：轮动调仓 (Sync_Portfolio)**：执行单次持仓差额比对并发出买卖委托。
- **核心组件 3：事件驱动订阅 (Subscribe_Quotes)**：对持仓标的发起 `xtdata.subscribe_quote`，并在 `on_tick_callback` 内部实现条件判断触发市价委托。
- **核心组件 4：已下单状态锁 (Order State Tracker)**：在内存中引入 `pending_orders` 集合或字典。当触发止盈下单时，首先尝试获取该标的的状态锁。如果已存在，则静默丢弃当前 Tick；下单动作必须异步执行（使用 `trader.order_stock_async` 或投递到本地线程安全队列），绝不允许阻塞底层的行情回调线程。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1:** 验证目标调仓名单的解析与比对
  - **Given** 存在 `target_positions.json` 且 QMT 返回当前持仓列表
  - **When** 运行 `Sync_Portfolio` 逻辑
  - **Then** 应正确计算出需要卖出的多余持仓以及需要买入的缺失持仓，并调用委托发送函数

- **Scenario 2:** 事件驱动止盈不爆 CPU
  - **Given** QMT 行情订阅成功
  - **When** 触发 `on_tick_callback` 且价格超过止盈阈值
  - **Then** 应执行卖出委托且不再使用死循环获取行情

- **Scenario 3:** 高频 Tick 下的防重（幂等性）测试
  - **Given** 某转债价格超过止盈阈值
  - **When** 系统在 100 毫秒内收到 5 个满足触发条件的 Tick 回调
  - **Then** 状态锁（Order State Tracker）应拦截后续 4 个请求，确保券商接口只收到 1 笔市价卖单委托

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **质量目标**：确保不使用 `while True` 轮询引发高 CPU 负载；杜绝任何由于并发 Tick 导致的超卖/废单风暴。
- **测试策略**：在独立的测试文件中通过 Mock `XtQuantTrader` 和 `xtdata` 来验证状态比对与买卖逻辑；编写并发 Tick 测试用力，快速向回调函数注入重复高价 Tick，断言下单函数仅被执行一次。

## 6. Framework Modifications (框架防篡改声明)
- `projects/AMS/windows_bridge/qmt_trader_sync.py` (新增)

## 7. Hardcoded Content (硬编码内容)

### Exact Text Replacements:
- **target_positions.json 文件路径**: 
  `"target_positions.json"`
- **断线提示文案**: 
  `"[-] 交易服务器连接断开"`
- **日志前缀 1**: 
  `"[委托回调]"`
- **日志前缀 2**: 
  `"[成交回调]"`