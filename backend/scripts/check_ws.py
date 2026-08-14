import sys
sys.path.insert(0, 'D:/sanate')
from backend.app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

print('Connecting to /ws/levels')
try:
    with client.websocket_connect('/ws/levels') as ws:
        print('Connected /ws/levels OK')
except Exception as e:
    print('Failed /ws/levels', type(e), e)

print('Connecting to /api/v1/chart/stream')
try:
    with client.websocket_connect('/api/v1/chart/stream') as ws:
        print('Connected /api/v1/chart/stream OK')
except Exception as e:
    print('Failed /api/v1/chart/stream', type(e), e)

print('Trying invalid channel /ws/unknown')
try:
    with client.websocket_connect('/ws/unknown') as ws:
        print('Unexpectedly connected unknown')
except Exception as e:
    print('Rejected unknown channel as expected:', type(e), e)
