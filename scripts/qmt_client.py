import httpx

class QMTClient:
    def __init__(self, base_url="http://43.134.76.215:8000"):
        self.base_url = base_url

    def health_check(self):
        resp = httpx.get(f"{self.base_url}/api/health")
        resp.raise_for_status()
        return resp.json()

    def get_full_tick(self):
        resp = httpx.get(f"{self.base_url}/api/bulk_quote")
        resp.raise_for_status()
        return resp.json()
