import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    client.connect('43.134.76.215', username='Administrator', password='8!9TYD.*Hm;ycV', timeout=10)
    
    commands = [
        'powershell "(Get-ChildItem -Path C:\\国金证券QMT交易端\\datadir\\Finance\\SZ\\86400 -Filter *.DAT).Count"',
        'powershell "(Get-ChildItem -Path C:\\国金证券QMT交易端\\datadir\\Finance\\SH\\86400 -Filter *.DAT).Count"'
    ]
    
    print("--- 统计本地财务数据文件数量 ---")
    for cmd in commands:
        stdin, stdout, stderr = client.exec_command(cmd)
        print(f"{cmd} => {stdout.read().decode('gbk', errors='ignore').strip()}")
        
except Exception as e:
    print(f"Error: {e}")
finally:
    client.close()
