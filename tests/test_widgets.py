import json


def get_token(client):
    response = client.post(
        "/auth/login", json={"email": "test@example.com", "password": "test"}
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_widget_crud(client):
    token = get_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    # Ensure baseline review so widgets can reflect data if needed
    data = [{"product": "card", "text": "solid", "date": "2023-01-01T00:00:00"}]
    files = {"file": ("reviews.json", json.dumps(data), "application/json")}
    upload_resp = client.post("/reviews/upload", files=files, headers=headers)
    assert upload_resp.status_code == 200

    create_resp = client.post(
        "/dashboard/widgets/",
        json={"title": "Total Reviews", "metric": "total_reviews"},
        headers=headers,
    )
    assert create_resp.status_code == 201
    body = create_resp.json()
    assert body["value"] >= 1
    assert body["visualization"] == "metric"
    widget_id = body["id"]

    list_resp = client.get("/dashboard/widgets/", headers=headers)
    assert list_resp.status_code == 200
    widgets = list_resp.json()
    assert any(w["id"] == widget_id for w in widgets)

    timeseries_resp = client.get(f"/dashboard/widgets/{widget_id}/timeseries", headers=headers)
    assert timeseries_resp.status_code == 200

    analytics_resp = client.get("/analytics/metric-trend/total_reviews", headers=headers)
    assert analytics_resp.status_code == 200

    delete_resp = client.delete(f"/dashboard/widgets/{widget_id}", headers=headers)
    assert delete_resp.status_code == 204

    list_resp = client.get("/dashboard/widgets/", headers=headers)
    assert list_resp.status_code == 200
    assert all(w["id"] != widget_id for w in list_resp.json())
