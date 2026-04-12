import sys
sys.path.append("/root/.openclaw/workspace/projects/AMS")
from scripts.qmt_client import QMTClient

client = QMTClient()
raw = client.get_full_tick(["000001.SZ", "00700.HK"])
print(type(raw))
if isinstance(raw, dict):
    for k, v in list(raw.items())[:2]:
        print(f"Key: {k}, Value type: {type(v)}, Value: {v}")
