import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path / "storage", run_worker=False)


@pytest.fixture
def client(app):
    with TestClient(app, base_url="http://localhost", headers={"X-Fabritake": "local"}) as client:
        yield client


@pytest.fixture
def demo(client):
    response = client.post("/api/demo")
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def runtime(app, client):
    return app.state.runtime
