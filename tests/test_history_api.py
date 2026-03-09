def test_chat_history_endpoints(app_client):
    client, app_module = app_client

    app_module.get_session_messages = lambda sid: [
        {"role": "user", "content": f"hello-{sid}"},
        {"role": "assistant", "content": "world"},
    ]

    cleared = {}

    def fake_clear_session_history(sid):
        cleared["sid"] = sid

    app_module.clear_session_history = fake_clear_session_history

    get_resp = client.get("/api/chat/history", params={"session_id": "s-1"})
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["session_id"] == "s-1"
    assert len(get_data["messages"]) == 2
    assert get_data["messages"][0]["content"] == "hello-s-1"

    empty_resp = client.get("/api/chat/history", params={"session_id": ""})
    assert empty_resp.status_code == 200
    assert empty_resp.json()["messages"] == []

    del_resp = client.delete("/api/chat/history", params={"session_id": "s-1"})
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True
    assert cleared["sid"] == "s-1"


def test_delete_chat_history_requires_session_id(app_client):
    client, _app_module = app_client

    resp = client.delete("/api/chat/history", params={"session_id": ""})

    assert resp.status_code == 400
    assert "session_id 不能为空" in resp.json()["detail"]
