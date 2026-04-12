from engine.event_engine import EventEngine, Event, EVENT_TICK
from engine.gateway import TickGateway
from unittest.mock import Mock, patch

@patch('scripts.qmt_client.QMTClient.get_full_tick')
def test_poll_once_with_flat_dict(mock_get_full_tick):
    # Mocking a flat dictionary response mapping codes to tick data
    mock_get_full_tick.return_value = {
        "000001.SZ": {"lastPrice": 15.5},
        "600000.SH": {"lastPrice": 10.2}
    }
    
    engine = EventEngine()
    received_events = []

    def handler(event: Event):
        received_events.append(event.data)

    engine.register(EVENT_TICK, handler)
    
    gateway = TickGateway()
    gateway.poll_once(engine)

    assert len(received_events) == 2
    assert {"code": "000001.SZ", "lastPrice": 15.5} in received_events
    assert {"code": "600000.SH", "lastPrice": 10.2} in received_events

@patch('scripts.qmt_client.QMTClient.get_full_tick')
def test_poll_once_with_wrapped_json(mock_get_full_tick):
    # Mocking a JSON envelope: {"status": "success", "data": {...}}
    mock_get_full_tick.return_value = {
        "status": "success",
        "data": {
            "510300.SH": {"lastPrice": 4.6}
        }
    }
    
    engine = EventEngine()
    received_events = []

    def handler(event: Event):
        received_events.append(event.data)

    engine.register(EVENT_TICK, handler)
    
    gateway = TickGateway()
    gateway.poll_once(engine)

    assert len(received_events) == 1
    assert {"code": "510300.SH", "lastPrice": 4.6} in received_events

@patch('scripts.qmt_client.QMTClient.get_full_tick')
def test_poll_once_with_invalid_data(mock_get_full_tick):
    # Mocking invalid data
    mock_get_full_tick.return_value = {
        "status": "success",
        "data": "not_a_dict_of_ticks"
    }
    
    engine = EventEngine()
    received_events = []

    def handler(event: Event):
        received_events.append(event.data)

    engine.register(EVENT_TICK, handler)
    
    gateway = TickGateway()
    gateway.poll_once(engine)

@patch('scripts.qmt_client.QMTClient.get_fundamentals')
def test_update_fundamentals_success(mock_get_fundamentals):
    mock_get_fundamentals.return_value = {
        "status": "success",
        "data": {
            "510300.SH": {"iopv": 4.4, "pe": 15.0}
        }
    }
    gateway = TickGateway()
    gateway.update_fundamentals()
    assert gateway.fundamentals_cache == {"510300.SH": {"iopv": 4.4, "pe": 15.0}}

@patch('scripts.qmt_client.QMTClient.get_full_tick')
def test_poll_once_merges_fundamentals_from_cache(mock_get_full_tick):
    mock_get_full_tick.return_value = {
        "status": "success",
        "data": {
            "510300.SH": {"lastPrice": 4.6}
        }
    }
    
    engine = EventEngine()
    received_events = []

    def handler(event: Event):
        received_events.append(event.data)

    engine.register(EVENT_TICK, handler)
    
    gateway = TickGateway()
    gateway.fundamentals_cache = {
        "510300.SH": {"iopv": 4.4, "pe": 15.0}
    }
    gateway.poll_once(engine)

    assert len(received_events) == 1
    assert {"code": "510300.SH", "lastPrice": 4.6, "iopv": 4.4, "pe": 15.0} in received_events

