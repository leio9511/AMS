import paramiko
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('43.134.76.215', username='Administrator', password='8!9TYD.*Hm;ycV', timeout=10)
stdin, stdout, stderr = client.exec_command('wmic process where "processid=4184" get ExecutablePath, CommandLine')
print(stdout.read().decode('gbk', errors='replace').strip())
client.close()
