from engine.event_engine import EventEngine, Event, EVENT_TICK
from engine.gateway import poll_once, TickGateway
from unittest.mock import Mock, patch

def test_event_engine_pub_sub():
    engine = EventEngine()
    handler_called = []

    def dummy_handler(event: Event):
        handler_called.append(event.data)

    engine.register(EVENT_TICK, dummy_handler)
    event = Event(type=EVENT_TICK, data={"price": 10})
    engine.process(event)

    assert len(handler_called) == 1
    assert handler_called[0] == {"price": 10}

def test_event_engine_unregister():
    engine = EventEngine()
    handler_called = []

    def dummy_handler(event: Event):
        handler_called.append(event.data)

    engine.register(EVENT_TICK, dummy_handler)
    engine.unregister(EVENT_TICK, dummy_handler)
    event = Event(type=EVENT_TICK, data={"price": 10})
    engine.process(event)

    assert len(handler_called) == 0

@patch('scripts.qmt_client.QMTClient.get_full_tick')
def test_gateway_poll_once(mock_get_full_tick):
    # Mocking a dictionary response mapping codes to tick data
    mock_get_full_tick.return_value = {
        "000001.SZ": {"lastPrice": 15.5},
        "600000.SH": {"lastPrice": 10.2}
    }
    
    engine = EventEngine()
    received_events = []

    def handler(event: Event):
        received_events.append(event.data)

    engine.register(EVENT_TICK, handler)
    poll_once(engine)

    assert len(received_events) == 2
    assert {"code": "000001.SZ", "lastPrice": 15.5} in received_events
    assert {"code": "600000.SH", "lastPrice": 10.2} in received_events
