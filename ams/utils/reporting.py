import json
import pandas as pd
from decimal import Decimal
from typing import Any, Dict

class DecimalEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, Decimal):
            return str(o)
        return super().default(o)

def generate_report_data(df_equity: pd.DataFrame, initial_cash: float) -> Dict[str, Any]:
    """
    Convert equity curve DataFrame into a standardized report structure.
    """
    if df_equity.empty:
        return {"summary": {}, "weekly_performance": []}
        
    df = df_equity.copy()
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)
    
    # Summary calculation
    initial_val = Decimal(str(initial_cash))
    final_val = Decimal(str(df['equity'].iloc[-1]))
    total_return = (final_val - initial_val) / initial_val
    
    df['hwm'] = df['equity'].cummax()
    df['drawdown'] = (df['equity'] - df['hwm']) / df['hwm']
    max_dd = Decimal(str(df['drawdown'].min()))
    
    calmar = total_return / abs(max_dd) if max_dd != 0 else Decimal('0')
    
    summary = {
        "total_return": total_return,
        "max_drawdown": max_dd,
        "calmar_ratio": calmar,
        "final_equity": final_val
    }
    
    # Weekly Performance (Resampled to Friday)
    weekly_series = df['equity'].resample('W-FRI').last().dropna()
    
    weekly_perf = []
    prev_equity = initial_val
    
    for date, equity in weekly_series.items():
        curr_equity = Decimal(str(equity))
        weekly_profit_pct = (curr_equity - prev_equity) / prev_equity
        cumulative_pct = (curr_equity - initial_val) / initial_val
        
        weekly_perf.append({
            "week_ending": str(date.date()),
            "total_assets": curr_equity,
            "weekly_profit_pct": weekly_profit_pct,
            "cumulative_pct": cumulative_pct
        })
        prev_equity = curr_equity
        
    return {
        "summary": summary,
        "weekly_performance": weekly_perf
    }

def format_json(report_data: Dict[str, Any]) -> str:
    """
    Format report data to a JSON string, serializing Decimals to strings.
    """
    return json.dumps(report_data, cls=DecimalEncoder, indent=2)

def format_text(report_data: Dict[str, Any]) -> str:
    """
    Format report data into a readable ASCII layout.
    """
    summary = report_data.get("summary", {})
    weekly_performance = report_data.get("weekly_performance", [])

    lines = []
    lines.append("=== Backtest Report ===")
    lines.append("Summary:")
    lines.append(f"  Total Return: {summary.get('total_return', 'N/A')}")
    lines.append(f"  Max Drawdown: {summary.get('max_drawdown', 'N/A')}")
    lines.append(f"  Calmar Ratio: {summary.get('calmar_ratio', 'N/A')}")
    lines.append(f"  Final Equity: {summary.get('final_equity', 'N/A')}")
    
    if weekly_performance:
        lines.append("")
        lines.append("Weekly Performance:")
        lines.append(f"  {'Week Ending':<15} | {'Total Assets':<15} | {'Weekly Profit %':<15} | {'Cumulative %':<15}")
        lines.append("-" * 72)
        for week in weekly_performance:
            lines.append(
                f"  {str(week.get('week_ending', 'N/A')):<15} | "
                f"{str(week.get('total_assets', 'N/A')):<15} | "
                f"{str(week.get('weekly_profit_pct', 'N/A')):<15} | "
                f"{str(week.get('cumulative_pct', 'N/A')):<15}"
            )
            
    return "\n".join(lines)
