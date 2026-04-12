import paramiko

windows_script = r"""
import sys
import time
import traceback
try:
    from xtquant import xtdata
    stocks = ['600519.SH']
    print("Downloading financial data for Moutai...")
    xtdata.download_financial_data(stocks, table_list=['Capital', 'Income'])
    time.sleep(2)
    
    data = xtdata.get_financial_data(stocks, table_list=['Capital', 'Income'])
    
    print("Moutai Capital:")
    capital = data.get('600519.SH', {}).get('Capital', [])
    if hasattr(capital, 'iloc') and not capital.empty:
        print(capital.iloc[-1]['total_capital'])
    elif isinstance(capital, list) and capital:
        print(capital[-1].get('total_capital'))
    else:
        print("Still None")

except Exception as e:
    traceback.print_exc()
"""

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('43.134.76.215', username='Administrator', password='8!9TYD.*Hm;ycV', timeout=10)

sftp = client.open_sftp()
with sftp.file('C:/Users/Administrator/Desktop/test_financial.py', 'w') as f:
    f.write(windows_script)
sftp.close()

stdin, stdout, stderr = client.exec_command('C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python310\\python.exe C:\\Users\\Administrator\\Desktop\\test_financial.py')
print(stdout.read().decode('gbk', 'ignore'))
print(stderr.read().decode('gbk', 'ignore'))
client.close()
