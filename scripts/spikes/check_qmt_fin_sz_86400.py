import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    client.connect('43.134.76.215', username='Administrator', password='8!9TYD.*Hm;ycV', timeout=10)
    
    commands = [
        'powershell "Get-ChildItem -Path C:\\国金证券QMT交易端\\datadir\\Finance\\SZ\\86400 | Select-Object Name, Length | Select-Object -First 10"'
    ]
    
    for cmd in commands:
        print(f"=== {cmd} ===")
        stdin, stdout, stderr = client.exec_command(cmd)
        print(stdout.read().decode('gbk', errors='ignore'))
        
except Exception as e:
    print(f"Error: {e}")
finally:
    client.close()
