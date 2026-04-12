from engine.event_engine import Event, EVENT_TICK
from scripts.qmt_client import QMTClient

class TickGateway:
    def __init__(self, qmt_client=None):
        self.qmt_client = qmt_client or QMTClient()
        self.fundamentals_cache = {}

    def update_fundamentals(self):
        try:
            response = self.qmt_client.get_fundamentals()
            if isinstance(response, dict):
                self.fundamentals_cache = response.get("data", response) if response.get("status") == "success" else response
        except Exception as e:
            print(f"Failed to update fundamentals cache: {e}")

    def poll_once(self, engine, code_list=None):
        response = self.qmt_client.get_full_tick(code_list)
        if isinstance(response, dict):
            tick_data = response.get("data", response) if response.get("status") == "success" else response
            if not isinstance(tick_data, dict):
                print(f"Gateway poll failed, unexpected data type: {type(tick_data)}")
                return
            
            for code, tick in tick_data.items():
                if code in ["status", "data"]: continue
                data_payload = {"code": code}
                if isinstance(tick, dict):
                    data_payload.update(tick)
                else:
                    data_payload["data"] = tick
                
                # O(1) In-memory merge from cache
                if code in self.fundamentals_cache and isinstance(self.fundamentals_cache[code], dict):
                    data_payload.update(self.fundamentals_cache[code])

                event = Event(type=EVENT_TICK, data=data_payload)
                engine.process(event)
        else:
            print(f"Gateway poll failed: {response}")

def poll_once(engine, code_list=None, qmt_client=None):
    """Convenience function as requested in PRD."""
    gw = TickGateway(qmt_client=qmt_client)
    gw.poll_once(engine, code_list)
