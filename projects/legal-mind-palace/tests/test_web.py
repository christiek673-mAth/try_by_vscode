from app.web import create_app


class FakePipeline:
    collection_name = "test_collection"

    def load_vector_store(self):
        return object()


def test_home_and_health_endpoint_are_available():
    client = create_app(FakePipeline()).test_client()

    assert client.get("/").status_code == 200
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.get_json() == {"collection": "test_collection", "ready": True}


def test_chat_validates_the_request_without_calling_model():
    client = create_app(FakePipeline()).test_client()

    response = client.post("/api/chat", json={"question": "", "top_k": 5})

    assert response.status_code == 400
    assert "question" in response.get_json()["error"]


def test_chat_rejects_top_k_outside_safe_range():
    client = create_app(FakePipeline()).test_client()

    response = client.post("/api/chat", json={"question": "测试", "top_k": 13})

    assert response.status_code == 400
    assert "top_k" in response.get_json()["error"]