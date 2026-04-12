from fastapi.testclient import TestClient
import json
import os
import pytest
from windows_bridge.server import app

client = TestClient(app)

def test_health_check():
    response = client.get('/api/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok', 'qmt_path': r'C:\国金证券QMT交易端\userdata_mini'}

def test_get_fundamentals_success(tmp_path, monkeypatch):
    # Mock a valid fundamentals.json on disk
    mock_file = tmp_path / "fundamentals.json"
    valid_data = {"000001.SZ": {"total_capital": 1000000, "total_equity": 500000, "net_profit": 10000}}
    mock_file.write_text(json.dumps(valid_data), encoding='utf-8')
    
    # Patch the OUTPUT_JSON_PATH in the module
    monkeypatch.setattr('windows_bridge.server.OUTPUT_JSON_PATH', str(mock_file))
    
    response = client.get('/api/fundamentals')
    assert response.status_code == 200
    assert response.json() == valid_data

def test_get_fundamentals_file_missing(tmp_path, monkeypatch):
    # Simulate missing fundamentals.json file
    missing_file = tmp_path / "missing.json"
    monkeypatch.setattr('windows_bridge.server.OUTPUT_JSON_PATH', str(missing_file))
    
    response = client.get('/api/fundamentals')
    assert response.status_code == 404
    assert response.json() == {"detail": "fundamentals.json not found"}

def test_get_fundamentals_file_malformed(tmp_path, monkeypatch):
    # Simulate malformed fundamentals.json file
    mock_file = tmp_path / "malformed.json"
    mock_file.write_text("{malformed_json", encoding='utf-8')
    
    monkeypatch.setattr('windows_bridge.server.OUTPUT_JSON_PATH', str(mock_file))
    
    response = client.get('/api/fundamentals')
    assert response.status_code == 500
    assert response.json() == {"detail": "fundamentals.json is malformed"}

def test_xtdata_call_success(monkeypatch):
    class MockXtData:
        @staticmethod
        def get_full_tick(args_list):
            return {"000001.SZ": {"lastPrice": 10.5}}
    
    import sys
    import types
    mock_xtquant = types.ModuleType('xtquant')
    mock_xtquant.xtdata = MockXtData
    sys.modules['xtquant'] = mock_xtquant
    
    payload = {
        "method": "get_full_tick",
        "args": [["000001.SZ"]]
    }
    response = client.post('/api/xtdata_call', json=payload)
    assert response.status_code == 200
    assert response.json() == {"status": "success", "data": {"000001.SZ": {"lastPrice": 10.5}}}
    
def test_xtdata_call_forbidden():
    payload = {
        "method": "os.system",
        "args": ["rm -rf /"]
    }
    response = client.post('/api/xtdata_call', json=payload)
    assert response.status_code == 403
    assert response.json() == {"detail": "Method not allowed"}
