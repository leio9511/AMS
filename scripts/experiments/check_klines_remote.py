import paramiko

windows_script = """
import json
import traceback

try:
    from xtquant import xtdata
    
    stocks = ['159501.SZ', '513100.SH', '159632.SZ', '159941.SZ', '513300.SH']
    res = {}
    
    st = '20240101'
    et = '20260412'
    
    # Try just fetching market data without relying on get_local_data
    # get_market_data might be safer and pull local data anyway.
    data_1d = xtdata.get_market_data(field_list=[], stock_list=stocks, period='1d', start_time=st, end_time=et, count=50)
    data_1m = xtdata.get_market_data(field_list=[], stock_list=stocks, period='1m', start_time=st, end_time=et, count=5000)
    
    for s in stocks:
        df_1d = data_1d.get(s)
        df_1m = data_1m.get(s)
        
        has_1d = df_1d is not None and not df_1d.empty
        has_1m = df_1m is not None and not df_1m.empty
        
        res[s] = {
            '1d_len': len(df_1d) if has_1d else 0,
            '1m_len': len(df_1m) if has_1m else 0,
        }
        if has_1d:
            res[s]['1d_sample_dates'] = [str(x) for x in df_1d.index[-2:]]
        if has_1m:
            res[s]['1m_sample_dates'] = [str(x) for x in df_1m.index[-2:]]
            
    print("===RESULT_START===")
    print(json.dumps(res, indent=2))
    print("===RESULT_END===")

except Exception as e:
    print("ERROR:")
    traceback.print_exc()
"""

with open('temp_check_klines.py', 'w', encoding='utf-8') as f:
    f.write(windows_script)

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('43.134.76.215', username='Administrator', password='8!9TYD.*Hm;ycV', timeout=10)

sftp = client.open_sftp()
sftp.put('temp_check_klines.py', 'C:/Users/Administrator/Desktop/temp_check_klines.py')
sftp.close()

stdin, stdout, stderr = client.exec_command('C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python310\\python.exe C:\\Users\\Administrator\\Desktop\\temp_check_klines.py')
print("STDOUT:", stdout.read().decode('gbk', 'ignore'))
print("STDERR:", stderr.read().decode('gbk', 'ignore'))

client.close()
