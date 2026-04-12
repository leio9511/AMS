import paramiko

windows_script = r"""
import os

def get_dir_size(path):
    total = 0
    for root, dirs, files in os.walk(path):
        for f in files:
            total += os.path.getsize(os.path.join(root, f))
    return total

finance_dir = r'C:\国金证券QMT交易端\userdata_mini\datadir\Finance'
print("--- Deep Finance Directory Check ---")
if os.path.exists(finance_dir):
    print(f"Total Finance Folder Size: {get_dir_size(finance_dir) / (1024*1024):.2f} MB")
    for d in os.listdir(finance_dir):
        sub_path = os.path.join(finance_dir, d)
        if os.path.isdir(sub_path):
            print(f"  Subdir: {d} - Size: {get_dir_size(sub_path) / (1024*1024):.2f} MB")
            files = os.listdir(sub_path)
            print(f"    File count: {len(files)}")
"""

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('43.134.76.215', username='Administrator', password='8!9TYD.*Hm;ycV', timeout=10)

sftp = client.open_sftp()
with sftp.file('C:/Users/Administrator/Desktop/check_finance_deep.py', 'w') as f:
    f.write(windows_script)
sftp.close()

stdin, stdout, stderr = client.exec_command('C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python310\\python.exe C:\\Users\\Administrator\\Desktop\\check_finance_deep.py')
print(stdout.read().decode('gbk', 'ignore'))
client.close()
