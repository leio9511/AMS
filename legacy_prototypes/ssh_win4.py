import paramiko
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('43.134.76.215', username='Administrator', password='8!9TYD.*Hm;ycV', timeout=10)
stdin, stdout, stderr = client.exec_command('powershell "Get-WmiObject Win32_Process -Filter \\"name=\'python.exe\'\\" | Select-Object CommandLine, ExecutablePath, __PATH"')
print(stdout.read().decode('gbk', errors='replace').strip())
client.close()
