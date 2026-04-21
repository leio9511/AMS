import json
from decimal import Decimal
from ams.utils.reporting import DecimalEncoder, format_json, format_text

def test_decimal_encoder_precision():
    data = {"value": Decimal('123.4567')}
    encoded = json.dumps(data, cls=DecimalEncoder)
    assert encoded == '{"value": "123.4567"}'

def test_precision_round_trip():
    data = {"value": Decimal('123.4567')}
    encoded = json.dumps(data, cls=DecimalEncoder)
    decoded = json.loads(encoded)
    assert Decimal(decoded["value"]) == data["value"]

def test_format_json_structure():
    report_data = {
        "summary": {
            "total_return": Decimal('0.15'),
            "max_drawdown": Decimal('0.05'),
            "calmar_ratio": Decimal('3.0'),
            "final_equity": Decimal('1150000.0')
        },
        "weekly_performance": [
            {
                "week_ending": "2026-03-01",
                "total_assets": Decimal('1050000.0'),
                "weekly_profit_pct": Decimal('0.05'),
                "cumulative_pct": Decimal('0.05')
            }
        ]
    }
    
    json_str = format_json(report_data)
    decoded = json.loads(json_str)
    
    assert "summary" in decoded
    assert "weekly_performance" in decoded
    assert decoded["summary"]["total_return"] == "0.15"
    assert decoded["summary"]["max_drawdown"] == "0.05"
    assert decoded["weekly_performance"][0]["week_ending"] == "2026-03-01"
    assert decoded["weekly_performance"][0]["total_assets"] == "1050000.0"

def test_format_text_output():
    report_data = {
        "summary": {
            "total_return": Decimal('0.15'),
            "max_drawdown": Decimal('0.05'),
            "calmar_ratio": Decimal('3.0'),
            "final_equity": Decimal('1150000.0')
        },
        "weekly_performance": [
            {
                "week_ending": "2026-03-01",
                "total_assets": Decimal('1050000.0'),
                "weekly_profit_pct": Decimal('0.05'),
                "cumulative_pct": Decimal('0.05')
            }
        ]
    }
    
    text_output = format_text(report_data)
    
    assert "=== Backtest Report ===" in text_output
    assert "Total Return: 0.15" in text_output
    assert "Max Drawdown: 0.05" in text_output
    assert "Weekly Performance:" in text_output
    assert "2026-03-01" in text_output
    assert "1050000.0" in text_output
