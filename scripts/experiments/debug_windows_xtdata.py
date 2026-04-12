import paramiko

windows_script = r"""
import os
import json
import time

try:
    from xtquant import xtdata
    
    # We suspect xtdata download or get_local_data is crashing
    # Let's try to just fetch whatever is in the CSV or database without xtdata first if possible
    # But QMT uses a proprietary .dat format.
    
    # Let's try the simplest possible call: get_instrument_detail
    print("DETAIL_START")
    stocks = ['159501.SZ', '513100.SH']
    for s in stocks:
        detail = xtdata.get_instrument_detail(s)
        print(f"{s}: {detail.get('InstrumentName')}")
    print("DETAIL_END")

    # Let's try to just download ONE stock and ONE day
    print("SINGLE_DOWNLOAD_START")
    xtdata.download_history_data('513100.SH', period='1d', start_time='20240410', end_time='20240411')
    print("SINGLE_DOWNLOAD_END")

except Exception as e:
    print(f"CRASH: {e}")
"""

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('43.134.76.215', username='Administrator', password='8!9TYD.*Hm;ycV', timeout=10)

sftp = client.open_sftp()
with sftp.file('C:/Users/Administrator/Desktop/debug_xtdata.py', 'w') as f:
    f.write(windows_script)
sftp.close()

stdin, stdout, stderr = client.exec_command('C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python310\\python.exe C:\\Users\\Administrator\\Desktop\\debug_xtdata.py')
print("STDOUT:", stdout.read().decode('gbk', 'ignore'))
print("STDERR:", stderr.read().decode('gbk', 'ignore'))
client.close()
