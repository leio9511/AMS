import json
from decimal import Decimal
from typing import Any, Dict

class DecimalEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, Decimal):
            return str(o)
        return super().default(o)

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
