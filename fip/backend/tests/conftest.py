import os
import tempfile

os.environ["DATA_PROVIDER"] = "synthetic"
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("REDIS_URL", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def auth(client):
    r = client.post("/api/v1/auth/register", json={"email": "trader@example.com", "password": "s3cure-pass"})
    assert r.status_code == 201
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
