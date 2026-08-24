from uuid import uuid4

from fastapi.testclient import TestClient

from ace.main import app

client = TestClient(app)


def test_dependency_map_not_found():
    random_uuid = uuid4()
    response = client.get(f"/dependencies/{random_uuid}?hops=1&direction=both")
    assert response.status_code == 404
    assert response.json()["detail"] == "Component not found"
