import sys

try:
    from xtquant import xtdata
    from xtquant.xttrader import XtQuanttrader
    print("SUCCESS: xtquant imported successfully.")
except ImportError as e:
    print(f"FAILURE: Could not import xtquant. Error: {e}")
except Exception as e:
    print(f"FAILURE: An unexpected error occurred: {e}")
