import argparse
import sys
import logging
from decimal import Decimal
from ams.core.factory import StrategyFactory
from ams.utils import reporting
from ams.core.history_datafeed import HistoryDataFeed
from ams.core.sim_broker import SimBroker
from ams.runners.backtest_runner import BacktestRunner
from ams.models.config import TakeProfitConfig, TakeProfitMode

# Ensure cb_rotation is registered
from ams.core.cb_rotation_strategy import CBRotationStrategy
StrategyFactory.register_strategy('cb_rotation')(CBRotationStrategy)

logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(
        description="Standardized Unified Backtest Entrypoint",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
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
    parser.add_argument('--data-path', default="/root/.openclaw/workspace/data/cb_history_factors.csv", help="Path to the historical data CSV file.")
    parser.add_argument('--format', choices=['text', 'json'], default='text', help="Output format ('text' or 'json'). Default: 'text'.")

    args = parser.parse_args()

    # Parameter Validation
    if args.tp_mode == 'both':
        if args.tp_pos is None or args.tp_intra is None:
            tp_mode = args.tp_mode
            raise ValueError(f"ERROR: --tp-mode '{tp_mode}' requires both --tp-pos and --tp-intra to be set.")

    # 1. TakeProfitConfig Construction
    tp_config = None
    if args.tp_mode:
        mode = TakeProfitMode(args.tp_mode)
        pos_thresh = Decimal(str(args.tp_pos)) if args.tp_pos is not None else None
        intra_thresh = Decimal(str(args.tp_intra)) if args.tp_intra is not None else None
        tp_config = TakeProfitConfig(mode=mode, pos_threshold=pos_thresh, intra_threshold=intra_thresh)

    # 2. Data Layer
    data_feed = HistoryDataFeed(file_path=args.data_path)

    # 3. Broker Layer
    broker = SimBroker(initial_cash=args.capital)

    # 4. Strategy Layer
    strategy = StrategyFactory.create_strategy(
        args.strategy,
        top_n=args.top_n,
        rebalance_period=args.rebalance,
        stop_loss_threshold=args.sl,
        tp_mode=args.tp_mode,
        tp_config=tp_config
    )

    # 5. Runner Layer
    runner = BacktestRunner(data_feed, broker, strategy)
    
    # 6. Execution
    df_equity = runner.run(args.start_date, args.end_date)
    report_data = reporting.generate_report_data(df_equity, args.capital)
            
    if args.format == 'json':
        print(reporting.format_json(report_data))
    else:
        print(reporting.format_text(report_data))

if __name__ == "__main__":
    try:
        main()
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        logger.exception("An unexpected error occurred during backtest execution.")
        sys.exit(1)
