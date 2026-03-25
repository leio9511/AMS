import paramiko
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('43.134.76.215', username='Administrator', password='8!9TYD.*Hm;ycV', timeout=10)
stdin, stdout, stderr = client.exec_command('powershell "Start-Process -FilePath \'C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python310\\python.exe\' -ArgumentList \'C:\\Users\\Administrator\\Desktop\\server.py\' -WindowStyle Hidden"')
print(stderr.read().decode('gbk', errors='replace').strip())
client.close()
