import json
from etf_tracker import fetch_etf_data, fetch_cb_data, THRESHOLD_ETF, THRESHOLD_CB

etfs = fetch_etf_data()
cbs = fetch_cb_data()

etf_anomalies = [e for e in etfs if abs(e['diff']) >= THRESHOLD_ETF]
cb_anomalies = [c for c in cbs if c['premium'] <= THRESHOLD_CB]

result = {
    "total_etfs_tracked": len(etfs),
    "total_cbs_tracked": len(cbs),
    "etf_anomalies": etf_anomalies,
    "cb_anomalies": cb_anomalies
}
print(json.dumps(result, ensure_ascii=False, indent=2))
