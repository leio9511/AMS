# QMT Financial Data Schema (F10)

This document is the single source of truth for QMT's local financial data (`.DAT` files) reverse-engineered via `xtdata.get_financial_data`. It serves as the foundation for the batch calculation engine.

## 1. Access Mechanism
- QMT downloads financial data into `C:\国金证券QMT交易端\datadir\Finance`.
- **CRITICAL DISCOVERY**: Setting `xtdata.data_dir` dynamically after `xtdata` has been imported in a long-running process (like FastAPI) **does not work** for financial data. The module locks in the path upon first initialization. To access the data via Python, we either need to set `xtdata.data_dir` before the first import, or symlink/copy the `Finance` folder to `userdata_mini/datadir/Finance`.
- The method used is: `xtdata.get_financial_data(['000001.SZ'], table_list=['Capital', 'Balance', 'Income', 'CashFlow'])`.

## 2. Table Structures & Key Fields

The data is returned as a nested dictionary: `{"000001.SZ": {"Capital": [DataFrame-like list of dicts], "Balance": [...], ...}}`.

### 2.1 Capital (股本结构)
Contains capital structure and share information.
- `m_timetag`: Publish Date (e.g., "19910403")
- `total_capital`: 总股本 (Total Shares)
- `circulating_capital`: 流通股本 (Circulating Shares)
- `restrict_circulating_capital`: 限售股本

### 2.2 Balance (资产负债表)
Contains balance sheet snapshot at the end of reporting periods.
- `m_timetag`: Statement Date (e.g., "19911231" for annual)
- `tot_assets`: 资产总计 (Total Assets)
- `tot_liab`: 负债合计 (Total Liabilities)
- `total_equity` / `tot_shrhldr_eqy_excl_min_int`: 股东权益合计 (Total Equity / Net Assets)
- `cash_equivalents`: 货币资金 (Cash & Equivalents)
- `undistributed_profit`: 未分配利润 (Undistributed Profit)

### 2.3 Income (利润表)
Contains income and profit details for the reporting period.
- `m_timetag`: Statement Date
- `revenue`: 营业收入 (Total Revenue)
- `oper_profit`: 营业利润 (Operating Profit)
- `tot_profit`: 利润总额 (Total Profit before tax)
- `net_profit_excl_min_int_inc`: 归属于母公司所有者的净利润 (Net Profit Attributable to Shareholders) - **Crucial for PE calculation**

### 2.4 CashFlow (现金流量表)
Contains cash flow metrics.
- `m_timetag`: Statement Date
- `net_cash_flows_oper_act`: 经营活动产生的现金流量净额 (Net Cash Flow from Operating Activities)
- `net_cash_flows_inv_act`: 投资活动产生的现金流量净额
- `net_cash_flows_fnc_act`: 筹资活动产生的现金流量净额

## 3. Data Characteristics & Quirks
1. **NaN Handling**: Missing values or empty fields are returned as `NaN` float values. These must be sanitized (e.g., converted to `None` or `0.0` depending on context) before being dumped into JSON.
2. **Timestamps**: Dates are represented as strings like `"19911231"` in the `m_timetag` field.
3. **Empty DataFrames**: If data is missing for a stock, `xtdata` returns an empty pandas DataFrame.

## 4. Next Steps for Issue 1043 (Calculator Engine)
To build the PE/PB/ROE calculator engine on Windows:
- **PE (市盈率)**: `lastPrice` (from Tick) / (`net_profit_excl_min_int_inc` / `total_capital`)
- **PB (市净率)**: `lastPrice` / (`total_equity` / `total_capital`)
- **ROE (净资产收益率)**: `net_profit_excl_min_int_inc` / `total_equity`
