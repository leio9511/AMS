from engine.event_engine import Event, EVENT_TICK
from scripts.qmt_client import QMTClient

class TickGateway:
    def __init__(self, qmt_client=None):
        self.qmt_client = qmt_client or QMTClient()

    def poll_once(self, engine, code_list=None):
        response = self.qmt_client.get_full_tick(code_list)
        # Handle both raw dict or success-wrapped dict
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
                event = Event(type=EVENT_TICK, data=data_payload)
                engine.process(event)
        else:
            print(f"Gateway poll failed: {response}")

def poll_once(engine, code_list=None, qmt_client=None):
    """Convenience function as requested in PRD."""
    gw = TickGateway(qmt_client=qmt_client)
    gw.poll_once(engine, code_list)
