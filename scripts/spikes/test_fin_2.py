import paramiko
import textwrap

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    client.connect('43.134.76.215', username='Administrator', password='8!9TYD.*Hm;ycV', timeout=10)
    
    script = textwrap.dedent("""
    import sys
    sys.path.insert(0, 'C:/Users/Administrator/AppData/Local/Programs/Python/Python310/Lib/site-packages')
    from xtquant import xtdata
    import json
    
    # Do not change data_dir, just use default (which is userdata_mini probably)
    print("Default data_dir:", xtdata.data_dir)
    
    try:
        # download first
        xtdata.download_financial_data(['000001.SZ'])
        data = xtdata.get_financial_data(['000001.SZ'], table_list=['Capital', 'Balance', 'Income', 'CashFlow'])
        
        result = {}
        for stock, tables in data.items():
            result[stock] = {}
            for table_name, df in tables.items():
                if not df.empty:
                    result[stock][table_name] = df.head(1).to_dict('records')
                else:
                    result[stock][table_name] = "Empty DataFrame"
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print("Error:", str(e))
    """)
    
    sftp = client.open_sftp()
    with sftp.file('test_fin_2.py', 'w') as f:
        f.write(script)
    sftp.close()
    
    stdin, stdout, stderr = client.exec_command('python test_fin_2.py')
    output = stdout.read().decode('gbk', errors='ignore')
    print(output)
    err = stderr.read().decode('gbk', errors='ignore')
    if err:
        print("STDERR:", err)
except Exception as e:
    print(f"Connection Error: {e}")
finally:
    client.close()
