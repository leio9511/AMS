---
Affected_Projects: [AMS]
---

# PRD: Event_Driven_Backtest_Architecture

## 1. Context & Problem (业务背景与核心痛点)
为了解决 ISSUE-1131（可转债轮动回测）以及 ISSUE-1127（实盘风控增强：强赎剔除、ST过滤、-8%止损），我们必须杜绝“回测代码与实盘代码分离”所导致的逻辑漂移与未来函数泄漏。当前的 AMS 代码库完全是过程化脚本（如 `crystal_fly_swatter.py`），把数据拉取、策略计算和报单输出揉在一起，无法进行回测，也无法安全接管实盘事件驱动逻辑。

## 2. Requirements & User Stories (需求定义)
我们必须构建一个微量化框架（Micro-framework），将业务核心（大脑）与外围基础设施（数据网关、交易执行）彻底物理分离。
- **Write Once, Run Anywhere**: 同一份策略代码既能跑历史回测，也能用于实盘交易。
- **Event-Driven**: 摒弃死循环轮询，系统响应数据切片事件。
- **本次任务范围（Phase 1）**: 
  1. 搭建基础微框架：定义抽象基类（`BaseStrategy`, `BaseDataFeed`, `BaseBroker`）。
  2. 实现回测四件套：实现 `HistoryDataFeed`、`SimBroker`、`BacktestRunner`。
  3. **应用绞杀者模式（Strangler Fig Pattern）重写策略**：在全新的 `ams/core/` 目录下从零构建 `CBRotationStrategy` 并适配回测框架。**绝对禁止**修改或侵入现网正在运行的 `crystal_fly_swatter.py` 或 `etf_tracker.py` 过程化脚本。旧代码在 Phase 2 双轨验证通过前必须原样保留，确保当前实盘业务零中断。
  *(注：Windows QMT的实盘执行引擎 `QMTBroker` 和 `LiveRunner` 将在下一阶段完成。)*

## 3. Architecture & Technical Strategy (架构设计与技术路线)
**微框架核心组件（4件套）：**
1. **策略引擎 (The Strategy)**
   - `BaseStrategy`: 提供 `on_bar(context, data)` 或 `generate_target_portfolio(context, data)` 抽象方法。
   - `CBRotationStrategy`: 继承基类，负责处理双低计算、ST剔除、-8%止损判断等纯粹的业务逻辑。
2. **数据网关 (The DataFeed)**
   - `BaseDataFeed`: 统一定义 `get_data(tickers, date)`。
   - `HistoryDataFeed`: 离线读取历史数据用于回测。
3. **交易网关 (The Broker)**
   - `BaseBroker`: 统一定义订单接口 `order_target_percent(ticker, percent)`。
   - `SimBroker`: 内存记账，扣减假资金，计算滑点。
4. **运行器 (The Runner)**
   - `BacktestRunner`: 回测循环调度器，按天拨动时钟，将历史数据推送给策略引擎，并将目标仓位发送给 `SimBroker` 结算，最终计算回撤和收益率曲线。

**代码目录隔离（目标蓝图）：**
- `ams/core/`: 存放基类接口和纯逻辑策略引擎。
- `ams/runners/`: 存放回测和实盘触发器脚本。
- `ams/windows_bridge/`: (本次暂不涉及) Windows端被动代理服务。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: 策略插件与框架解耦**
  - **Given** 一个实现好的 `BacktestRunner` 和模拟环境
  - **When** 注入 `CBRotationStrategy` 并配置 2024 年初至今回测时段
  - **Then** Runner 应该能驱动策略每天执行，并输出回测资金曲线报告，且 `CBRotationStrategy` 中无任何发起网络拉取数据的硬编码。

- **Scenario 2: 回测撮合引擎的执行**
  - **Given** 策略输出目标持仓（Target Portfolio）信号
  - **When** `SimBroker` 接收到订单并撮合当天历史数据
  - **Then** `SimBroker` 应正确扣减账户虚拟资金，模拟买卖交易，并更新当前持仓 Context。

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **核心质量风险**: 回测引擎是否准确无误地管理了模拟时间线，杜绝了未来数据泄漏。
- **Mocking**: 单元测试中应对 `HistoryDataFeed` 伪造假的市场行情数据。
- **TDD指导**: 重点测试 `SimBroker` 的账本扣减逻辑和滑点计算，确保模拟回测与数学逻辑严格对齐。

## 6. Framework Modifications (框架防篡改声明)
- 无，主要是基于已有模块的重构和新增框架脚本。

## 7. Hardcoded Content (硬编码内容)
- None