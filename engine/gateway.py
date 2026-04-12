from engine.event_engine import Event, EVENT_TICK
from scripts.qmt_client import QMTClient

class TickGateway:
    def __init__(self, qmt_client=None):
        self.qmt_client = qmt_client or QMTClient()

    def poll_once(self, engine, code_list=None):
        tick_data = self.qmt_client.get_full_tick(code_list)
        if isinstance(tick_data, dict):
            # Assuming get_full_tick returns a dict: { "000001.SZ": { tick dict }, ... }
            for code, tick in tick_data.items():
                # We might want to include the code inside the tick data or as a separate field
                # PRD: "transforms the dictionary response into multiple Event objects pushed to the engine."
                data_payload = {"code": code}
                data_payload.update(tick if isinstance(tick, dict) else {"data": tick})
                event = Event(type=EVENT_TICK, data=data_payload)
                engine.process(event)

def poll_once(engine, code_list=None, qmt_client=None):
    """Convenience function as requested in PRD."""
    gw = TickGateway(qmt_client=qmt_client)
    gw.poll_once(engine, code_list)
