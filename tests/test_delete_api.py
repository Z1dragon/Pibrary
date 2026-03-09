def test_delete_file_and_note_endpoints(app_client):
    client, app_module = app_client

    app_module.delete_file = lambda _file_path: True
    app_module.delete_note = lambda _note_id: True

    file_resp = client.delete("/api/kb/file", params={"file_path": "data/raw/book.md"})
    assert file_resp.status_code == 200
    assert file_resp.json()["success"] is True

    note_resp = client.delete("/api/notes", params={"note_id": "note-1"})
    assert note_resp.status_code == 200
    assert note_resp.json()["success"] is True


def test_delete_file_and_note_failures(app_client):
    client, app_module = app_client

    app_module.delete_file = lambda _file_path: False
    app_module.delete_note = lambda _note_id: False

    file_resp = client.delete("/api/kb/file", params={"file_path": "data/raw/book.md"})
    assert file_resp.status_code == 400
    assert "删除失败" in file_resp.json()["detail"]

    note_resp = client.delete("/api/notes", params={"note_id": "note-1"})
    assert note_resp.status_code == 400
    assert "笔记删除失败" in note_resp.json()["detail"]
