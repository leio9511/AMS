import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    client.connect('43.134.76.215', username='Administrator', password='8!9TYD.*Hm;ycV', timeout=10)
    
    # Create Finance dir in userdata_mini and copy 000001.SZ over
    commands = [
        'powershell "New-Item -ItemType Directory -Force -Path C:\\国金证券QMT交易端\\userdata_mini\\datadir\\Finance\\SZ\\86400"',
        'powershell "Copy-Item -Path C:\\国金证券QMT交易端\\datadir\\Finance\\SZ\\86400\\000001_* -Destination C:\\国金证券QMT交易端\\userdata_mini\\datadir\\Finance\\SZ\\86400 -Force"',
        'powershell "Get-ChildItem -Path C:\\国金证券QMT交易端\\userdata_mini\\datadir\\Finance\\SZ\\86400"'
    ]
    
    for cmd in commands:
        print(f"=== {cmd} ===")
        stdin, stdout, stderr = client.exec_command(cmd)
        print(stdout.read().decode('gbk', errors='ignore'))
        
except Exception as e:
    print(f"Error: {e}")
finally:
    client.close()
