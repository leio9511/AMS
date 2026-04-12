import paramiko

windows_script = r"""
import sys
import time
from xtquant import xtdata

def check_finance():
    sample = ['600519.SH', '000858.SZ']
    try:
        data = xtdata.get_financial_data(sample, table_list=['Capital', 'Income'])
        capital = data.get('600519.SH', {}).get('Capital', [])
        
        has_data = False
        if hasattr(capital, 'empty'):
            has_data = not capital.empty
        else:
            has_data = bool(capital)
            
        if has_data:
            print("SUCCESS: 600519.SH data fetched successfully! Data download worked.")
            print("Capital record count:", len(capital))
        else:
            print("WARNING: Data is still empty. Download may still be in progress, or QMT server is not responding to downloads tonight.")
            
    except Exception as e:
        print(f"Error checking data: {e}")

if __name__ == "__main__":
    check_finance()
"""

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('43.134.76.215', username='Administrator', password='8!9TYD.*Hm;ycV', timeout=10)

sftp = client.open_sftp()
with sftp.file('C:/Users/Administrator/Desktop/check_finance_after.py', 'w') as f:
    f.write(windows_script)
sftp.close()

stdin, stdout, stderr = client.exec_command('C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python310\\python.exe C:\\Users\\Administrator\\Desktop\\check_finance_after.py')
print(stdout.read().decode('gbk', 'ignore'))
client.close()
