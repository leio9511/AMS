from fastapi.testclient import TestClient
from qmt_bridge_server import app

client = TestClient(app)

def test_health_check():
    response = client.get('/api/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok', 'qmt_path': r'C:\国金证券QMT交易端\userdata_mini'}
