import paramiko
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    client.connect('43.134.76.215', username='Administrator', password='8!9TYD.*Hm;ycV', timeout=10)
    
    stdin, stdout, stderr = client.exec_command('type "C:\\Users\\Administrator\\Desktop\\server.py"')
    print(stdout.read().decode('utf-8', errors='ignore'))
except Exception as e:
    print(f"Error: {e}")
finally:
    client.close()
