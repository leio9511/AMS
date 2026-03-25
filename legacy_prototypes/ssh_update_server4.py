import paramiko
code = """import uvicorn
from fastapi import FastAPI
import sys

app = FastAPI(title='miniQMT Bridge')

@app.get('/')
def health_check():
    return {'status': 'ok', 'qmt_path': r'C:\\国金证券QMT交易端\\userdata_mini'}

@app.get('/api/probe')
def probe_qmt_data():
    try:
        from xtquant import xtdata
        stock = "600000.SH"
        tick = xtdata.get_full_tick([stock])
        detail = xtdata.get_instrument_detail(stock)
        return {
            "probe_tick": tick,
            "probe_detail": detail
        }
    except Exception as e:
        return {"error": str(e)}

@app.get('/api/bulk_quote')
def bulk_quote():
    try:
        from xtquant import xtdata
        # Fake it or fetch it
        return xtdata.get_full_tick([])
    except Exception as e:
        return {"error": str(e), "data": {}}

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=8000)
"""

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('43.134.76.215', username='Administrator', password='8!9TYD.*Hm;ycV', timeout=10)

sftp = client.open_sftp()
with sftp.file('C:\\Users\\Administrator\\Desktop\\server.py', 'w') as f:
    f.write(code.encode('utf-8'))
sftp.close()

stdin, stdout, stderr = client.exec_command('wmic process where "commandline like \'%server.py%\' and name=\'python.exe\'" get processid')
out = stdout.read().decode('gbk', errors='replace').strip().split('\n')
for line in out:
    line = line.strip()
    if line.isdigit():
        client.exec_command(f'taskkill /F /PID {line}')

client.exec_command('wmic process call create "C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python310\\python.exe C:\\Users\\Administrator\\Desktop\\server.py"')
client.close()
