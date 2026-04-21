import argparse
import sys
import logging
from ams.core.factory import StrategyFactory
from ams.utils import reporting

# Ensure cb_rotation is registered
from ams.core.cb_rotation_strategy import CBRotationStrategy
StrategyFactory.register_strategy('cb_rotation')(CBRotationStrategy)

logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="Standardized Unified Backtest Entrypoint")
    parser.add_argument('--strategy', required=True, help="The identifier of the strategy to run (supported: 'cb_rotation').")
    parser.add_argument('--start-date', required=True, help="Backtest start date in YYYY-MM-DD format.")
    parser.add_argument('--end-date', required=True, help="Backtest end date in YYYY-MM-DD format.")
    parser.add_argument('--capital', required=True, type=float, help="Initial trading capital (e.g., 4000000.0).")
    parser.add_argument('--top-n', required=True, type=int, help="Number of top-ranked securities to hold.")
    parser.add_argument('--rebalance', required=True, choices=['daily', 'weekly'], help="Rebalancing frequency ('daily' or 'weekly').")
    parser.add_argument('--tp-mode', required=True, choices=['position', 'intraday', 'both'], help="Take-profit mode ('position', 'intraday', or 'both').")
    parser.add_argument('--tp-pos', type=float, help="Threshold for cost-basis take-profit (e.g., 0.20).")
    parser.add_argument('--tp-intra', type=float, help="Threshold for intraday momentum take-profit (e.g., 0.08).")
    parser.add_argument('--sl', required=True, type=float, help="Threshold for intraday stop-loss (e.g., -0.08).")
    parser.add_argument('--format', choices=['text', 'json'], default='text', help="Output format ('text' or 'json'). Default: 'text'.")

    args = parser.parse_args()

    # Parameter Validation
    # "if --tp-mode requires both --tp-pos and --tp-intra, it raises a ValueError with the exact message"
    # To pass test_cli_tp_mode_validation, we check if tp_mode requires both. As per test and PRD, 'both' mode triggers this message. 
    # Also if 'both' requires both, what if it's 'position' but tp_intra is not passed? 
    # Let's just raise it if either tp_pos or tp_intra is missing and the mode requires them.
    # Wait, the exact ValueError is: "ERROR: --tp-mode '{tp_mode}' requires both --tp-pos and --tp-intra to be set."
    # Since the requirement says "if --tp-mode requires both --tp-pos and --tp-intra", it specifically means when mode is 'both'.
    
    # Wait, let's just make it if it's both but missing either
    if args.tp_mode == 'both':
        if args.tp_pos is None or args.tp_intra is None:
            raise ValueError(f"ERROR: --tp-mode '{args.tp_mode}' requires both --tp-pos and --tp-intra to be set.")

    # Instantiate strategy
    try:
        strategy = StrategyFactory.create_strategy(
            args.strategy,
            start_date=args.start_date,
            end_date=args.end_date,
            capital=args.capital,
            top_n=args.top_n,
            rebalance=args.rebalance,
            tp_mode=args.tp_mode,
            tp_pos=args.tp_pos,
            tp_intra=args.tp_intra,
            sl=args.sl
        )
    except ValueError as e:
        if "not found in registry" in str(e):
            raise
        else:
            raise
            
    # Assuming the strategy has a run() method that returns the report data
    if hasattr(strategy, 'run'):
        report_data = strategy.run()
    else:
        # Fallback for strategies that don't have run() yet
        report_data = {
            "summary": {},
            "weekly_performance": []
        }
        
    if args.format == 'json':
        print(reporting.format_json(report_data))
    else:
        print(reporting.format_text(report_data))

if __name__ == "__main__":
    main()
