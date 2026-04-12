import paramiko

windows_script = r"""
import sys
import time
from xtquant import xtdata

def download_all_finance():
    print("Starting financial data download...")
    # Get all A-shares
    stocks = xtdata.get_stock_list_in_sector('沪深A股')
    print(f"Total stocks to download: {len(stocks)}")
    
    if not stocks:
        print("Failed to get stock list. QMT might be disconnected.")
        return

    # To prevent overwhelming the connection and timing out entirely on Sunday night, 
    # let's download in a batch or just trigger the whole list.
    try:
        print("Sending download command to QMT...")
        xtdata.download_financial_data(stocks, table_list=['Capital', 'Income'])
        print("Download command sent successfully.")
    except Exception as e:
        print(f"Error downloading: {e}")
        return
        
    print("Waiting 15 seconds to check if data is arriving...")
    time.sleep(15)
    
    # Check if data is populated for a sample stock
    sample = ['600519.SH']
    try:
        data = xtdata.get_financial_data(sample, table_list=['Capital', 'Income'])
        capital = data.get('600519.SH', {}).get('Capital', [])
        
        has_data = False
        if hasattr(capital, 'empty'):
            has_data = not capital.empty
        else:
            has_data = bool(capital)
            
        if has_data:
            print("SUCCESS: Sample data (600519.SH) fetched successfully! QMT server is providing data.")
        else:
            print("WARNING: Sample data is still empty. The broker server might be down for Sunday maintenance, or download is still in progress.")
    except Exception as e:
        print(f"Error checking data: {e}")

if __name__ == "__main__":
    download_all_finance()
"""

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('43.134.76.215', username='Administrator', password='8!9TYD.*Hm;ycV', timeout=10)

sftp = client.open_sftp()
with sftp.file('C:/Users/Administrator/Desktop/download_finance.py', 'w') as f:
    f.write(windows_script)
sftp.close()

stdin, stdout, stderr = client.exec_command('C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python310\\python.exe C:\\Users\\Administrator\\Desktop\\download_finance.py', timeout=120)
print(stdout.read().decode('gbk', 'ignore'))
print(stderr.read().decode('gbk', 'ignore'))
client.close()
