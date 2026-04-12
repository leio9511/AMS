import paramiko

windows_script = r"""
from xtquant import xtdata
import json

# Use the older but stable get_local_data
stocks = ['159501.SZ', '513100.SH', '159632.SZ', '159941.SZ', '513300.SH']
print("BATCH_START")
try:
    # Attempt to fetch as dict of lists/arrays instead of DataFrames if possible
    # though get_local_data usually returns DataFrames.
    data = xtdata.get_local_data(field_list=['close'], stock_list=stocks, period='1d', count=30)
    for s in stocks:
        if s in data:
            df = data[s]
            if df is not None and not df.empty:
                print(f"RES:{s}:{len(df)}")
                # Just print the last 5 days
                subset = df.tail(5)
                for date, row in subset.iterrows():
                    print(f"D:{s}:{date}:{row['close']}")
except Exception as e:
    print(f"CRASH:{e}")
print("BATCH_END")
"""

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('43.134.76.215', username='Administrator', password='8!9TYD.*Hm;ycV', timeout=10)

sftp = client.open_sftp()
with sftp.file('C:/Users/Administrator/Desktop/batch_pull.py', 'w') as f:
    f.write(windows_script)
sftp.close()

stdin, stdout, stderr = client.exec_command('C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python310\\python.exe C:\\Users\\Administrator\\Desktop\\batch_pull.py')
print(stdout.read().decode('gbk', 'ignore'))
client.close()
