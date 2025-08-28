import json


def get_token(client):
    response = client.post("/auth/login", json={"username": "test", "password": "test"})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_upload_and_list_reviews(client):
    token = get_token(client)
    data = [{"product": "card", "text": "good card", "date": "2023-01-01T00:00:00"}]
    files = {"file": ("reviews.json", json.dumps(data), "application/json")}
    upload_resp = client.post("/reviews/upload", files=files, headers={"Authorization": f"Bearer {token}"})
    assert upload_resp.status_code == 200
    list_resp = client.get("/reviews", headers={"Authorization": f"Bearer {token}"})
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


def test_stats_endpoint(client):
    token = get_token(client)
    resp = client.get("/reviews/stats", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_timeseries_endpoint(client):
    token = get_token(client)
    resp = client.get("/reviews/timeseries", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
