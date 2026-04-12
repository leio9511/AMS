import httpx

class QMTClient:
    def __init__(self, base_url="http://43.134.76.215:8000"):
        self.base_url = base_url

    def health_check(self):
        resp = httpx.get(f"{self.base_url}/api/health")
        resp.raise_for_status()
        return resp.json()

    def get_fundamentals(self):
        try:
            resp = httpx.get(f"{self.base_url}/api/fundamentals")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_full_tick(self, code_list=None):
        payload = {
            "method": "get_full_tick",
            "args": [code_list] if code_list else [],
            "kwargs": {}
        }
        resp = httpx.post(f"{self.base_url}/api/xtdata_call", json=payload)
        resp.raise_for_status()
        res_json = resp.json()
        if res_json.get("status") == "success":
            return res_json.get("data")
        return res_json  # or handle error
