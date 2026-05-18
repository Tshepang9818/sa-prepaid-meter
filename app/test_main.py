import sys
from unittest.mock import MagicMock, patch

sys.modules['psycopg2'] = MagicMock()
sys.modules['redis'] = MagicMock()
sys.modules['requests'] = MagicMock()
sys.modules['prometheus_fastapi_instrumentator'] = MagicMock()

with patch('psycopg2.connect'), patch('redis.from_url'):
    from main import app

from fastapi.testclient import TestClient
client = TestClient(app)

def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "SA Prepaid Meter Monitor"

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_health_has_timestamp():
    response = client.get("/health")
    assert "timestamp" in response.json()

def test_root_has_appliances():
    response = client.get("/")
    assert "appliances_tracked" in response.json()
    assert "geyser" in response.json()["appliances_tracked"]
