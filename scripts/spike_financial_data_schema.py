# projects/AMS/scripts/spike_financial_data_schema.py

import httpx
import json
import time

QMT_BRIDGE_URL = "http://43.134.76.215:8000"

def call_xtdata(method, args=None, kwargs=None, timeout=30):
    """Generic function to call the xtdata_call endpoint."""
    if args is None:
        args = []
    if kwargs is None:
        kwargs = {}
        
    url = f"{QMT_BRIDGE_URL}/api/xtdata_call"
    payload = {
        "method": method,
        "args": args,
        "kwargs": kwargs
    }
    try:
        print(f"[*] Calling method: {method} with args: {args}, kwargs: {kwargs}")
        response = httpx.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        print(f"[+] Response for {method}:")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return data
    except httpx.HTTPStatusError as e:
        print(f"[!] HTTP Error for {method}: {e.response.status_code} - {e.response.text}")
    except httpx.RequestError as e:
        print(f"[!] Request Error for {method}: {e}")
    except json.JSONDecodeError as e:
        print(f"[!] JSON Decode Error for {method}: {e}")
        print(f"    Raw response: {response.text}")
    return None

def main():
    """
    Main function to run the spike tests.
    """
    print("--- Starting QMT Financial Data Schema Spike ---")
    
    # --- Step 1: Health Check ---
    print("\n[--- Step 1: Health Check ---]")
    try:
        health = httpx.get(f"{QMT_BRIDGE_URL}/api/health").json()
        if health.get("status") == "ok":
            print("[+] QMT Bridge is online.")
        else:
            print("[!] QMT Bridge health check failed. Aborting.")
            return
    except Exception as e:
        print(f"[!] Could not connect to QMT Bridge: {e}. Aborting.")
        return

    # --- Step 2: Try to get a list of tables ---
    print("\n[--- Step 2: Attempting to list all financial tables (Hypothetical) ---]")
    # This is a guess. The method might not exist.
    call_xtdata('list_financial_tables')
    call_xtdata('help')

    # --- Step 3: Probe specific, common table names ---
    print("\n[--- Step 3: Probing specific financial data tables for '600519.SH' ---]")
    test_stock = '600519.SH'
    
    # Based on xtquant documentation and previous attempts
    common_tables = [
        # Main Financial Statements (as seen in docs)
        'Balance', 
        'Income', 
        'CashFlow',
        # Detailed Tables (from xtquant docs)
        'STK_FINANCE_QUART_DATA',
        'STK_FINANCE_ANN_DATA',
        'STK_CAP_DATA',
        'STK_HOLDER_NUM_DATA',
        'STK_TOP10_HOLDER_DATA',
        'STK_TOP10_FLO_HOLDER_DATA',
        'STK_PERSHARE_INDEX_DATA',
        # Other potential names (from my memory/experience)
        'Capital',
        'HolderNum',
        'Top10Holder',
        'Top10FlowHolder',
        'PershareIndex'
    ]
    
    for table in common_tables:
        print(f"\n--- Probing table: {table} ---")
        call_xtdata('get_financial_data', 
                    args=[[test_stock]], 
                    kwargs={'table_list': [table]})
        time.sleep(1) # Be nice to the server

    print("\n--- Spike Test Complete ---")
    print("Review the output above to identify which tables returned data.")
    print("If all are empty, the QMT client on the server may not be logged in or the data source is unavailable.")


if __name__ == "__main__":
    main()
