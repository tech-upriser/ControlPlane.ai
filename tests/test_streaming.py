from fastapi.testclient import TestClient
from app.main import app

def test_health():
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

def test_streaming_response():
    with TestClient(app) as client:
        resp = client.post(
            "/v1/chat/completions",
            json={"model": "mock", "messages": [{"role": "user", "content": "Hi"}], "stream": True}
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        body = resp.text
        assert "data:" in body
        assert "[DONE]" in body
