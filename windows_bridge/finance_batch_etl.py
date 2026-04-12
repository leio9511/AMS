import math
import json
import os

try:
    import xtquant.xtdata as xtdata
    QMT_DATA_DIR = 'C:/国金证券QMT交易端/datadir'
    xtdata.data_dir = QMT_DATA_DIR
except ImportError:
    xtdata = None

OUTPUT_JSON_PATH = 'C:/Users/Administrator/Desktop/fundamentals.json'

def sanitize_value(val):
    if val is None:
        return None
    try:
        if math.isnan(val):
            return None
    except TypeError:
        pass
    return val

def process_financial_data(stock_list):
    if not xtdata:
        print("xtdata module not available")
        return {}
    
    table_list = ['Capital', 'Balance', 'Income']
    chunk_size = 500
    results = {}
    
    for i in range(0, len(stock_list), chunk_size):
        chunk = stock_list[i:i+chunk_size]
        data = xtdata.get_financial_data(chunk, table_list=table_list)
        
        for stock in chunk:
            stock_data = data.get(stock, {})
            capital_data = stock_data.get('Capital', [])
            balance_data = stock_data.get('Balance', [])
            income_data = stock_data.get('Income', [])
            
            total_capital = None
            if capital_data is not None and not capital_data.empty:
                # If it is a DataFrame, get value from first row. Handle both Dict/List and DataFrame shapes.
                try:
                    total_capital = capital_data.iloc[-1]['total_capital'] if hasattr(capital_data, 'iloc') else capital_data[0].get('total_capital')
                except (KeyError, IndexError):
                    total_capital = None
            
            total_equity = None
            if balance_data is not None and not balance_data.empty:
                try:
                    row = balance_data.iloc[-1] if hasattr(balance_data, 'iloc') else balance_data[0]
                    total_equity = row.get('tot_shrhldr_eqy_excl_min_int') if isinstance(row, dict) else row.get('tot_shrhldr_eqy_excl_min_int')
                    if total_equity is None or (isinstance(total_equity, float) and math.isnan(total_equity)):
                        total_equity = row.get('total_equity')
                except (KeyError, IndexError):
                    total_equity = None
            
            net_profit = None
            if income_data is not None and not income_data.empty:
                try:
                    row = income_data.iloc[-1] if hasattr(income_data, 'iloc') else income_data[0]
                    net_profit = row.get('net_profit_excl_min_int_inc') if isinstance(row, dict) else row.get('net_profit_excl_min_int_inc')
                except (KeyError, IndexError):
                    net_profit = None
                
            results[stock] = {
                'total_capital': sanitize_value(total_capital),
                'total_equity': sanitize_value(total_equity),
                'net_profit': sanitize_value(net_profit)
            }
            
    return results

def main():
    if not xtdata:
        return
    stock_list = xtdata.get_stock_list_in_sector('沪深A股')
    fundamentals = process_financial_data(stock_list)
    
    with open(OUTPUT_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(fundamentals, f, ensure_ascii=False, indent=2)

if __name__ == '__main__':
    main()