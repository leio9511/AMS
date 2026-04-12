import paramiko

windows_script = r"""
import os
import json

def get_dir_size(path):
    total = 0
    try:
        with os.scandir(path) as it:
            for entry in it:
                if entry.is_file():
                    total += entry.stat().st_size
                elif entry.is_dir():
                    total += get_dir_size(entry.path)
    except:
        pass
    return total

paths = [
    'C:\\国金证券QMT交易端\\userdata_mini\\datadir',
    'C:\\国金证券QMT交易端\\bin.x64\\userdata_mini\\datadir',
    'C:\\Users\\Administrator\\Desktop\\AMS'
]

report = {}
for p in paths:
    if os.path.exists(p):
        try:
            subdirs = [d for d in os.listdir(p) if os.path.isdir(os.path.join(p, d))]
            report[p] = {
                "exists": True,
                "subdirs": subdirs,
                "total_size_mb": round(get_dir_size(p) / (1024 * 1024), 2)
            }
        except:
            report[p] = {"exists": True, "error": "access denied"}
    else:
        report[p] = {"exists": False}

print("===DISK_SCAN_START===")
print(json.dumps(report, indent=2))
print("===DISK_SCAN_END===")
"""

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('43.134.76.215', username='Administrator', password='8!9TYD.*Hm;ycV', timeout=10)

sftp = client.open_sftp()
with sftp.file('C:/Users/Administrator/Desktop/disk_scan.py', 'w') as f:
    f.write(windows_script)
sftp.close()

stdin, stdout, stderr = client.exec_command('C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python310\\python.exe C:\\Users\\Administrator\\Desktop\\disk_scan.py')
print(stdout.read().decode('gbk', 'ignore'))
client.close()
