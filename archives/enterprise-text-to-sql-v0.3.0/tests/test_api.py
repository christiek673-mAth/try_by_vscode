from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_demo_query_is_tenant_scoped_and_masks_sensitive_data():
    response = client.post(
        "/v1/query",
        json={"question": "查询客户", "tenant_id": "demo", "user_id": "tester"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "mock-local"
    assert body["row_count"] == 2
    assert body["sql"].lower().count("tenant_id") == 1
    assert all(row["email"] == "***MASKED***" for row in body["rows"])


def test_dry_run_does_not_execute_query():
    response = client.post(
        "/v1/query",
        json={"question": "查询订单", "tenant_id": "demo", "execute": False},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["rows"] == []
    assert body["execution_ms"] is None
    assert "tenant_id" in body["sql"]


def test_catalog_hides_sensitive_columns():
    response = client.get("/v1/catalog")

    assert response.status_code == 200
    columns = {
        column["name"]
        for table in response.json()
        for column in table["columns"]
    }
    assert "email" not in columns