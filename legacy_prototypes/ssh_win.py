import paramiko

def run_cmd(cmd):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect('43.134.76.215', username='Administrator', password='8!9TYD.*Hm;ycV', timeout=10)
        stdin, stdout, stderr = client.exec_command(cmd)
        out = stdout.read().decode('gbk', errors='replace').strip()
        err = stderr.read().decode('gbk', errors='replace').strip()
        print(f"--- CMD: {cmd} ---")
        if out: print("STDOUT:\n" + out)
        if err: print("STDERR:\n" + err)
    except Exception as e:
        print("Error:", e)
    finally:
        client.close()

run_cmd('dir C:\\Users\\Administrator\\Desktop')
run_cmd('dir C:\\国金证券QMT交易端')
run_cmd('powershell "Get-ChildItem -Path C:\\ -Filter *server.py -Recurse -ErrorAction SilentlyContinue"')
