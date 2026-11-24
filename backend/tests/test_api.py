from filelock import FileLock, Timeout
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.exc import IntegrityError

from app.application.projects import scenes
from app.infrastructure.database import Scene
from app.infrastructure.providers import BrowserInstanceManager
from app.runtime import Runtime


def test_restricts_writes_and_host(app, client):
    payload = {"name": "Teste", "provider": "simulated"}
    assert client.post("/api/instances", json=payload, headers={"Origin": "https://example.com"}).status_code == 403
    assert client.post("/api/instances", json=payload, headers={"X-Fabritake": ""}).status_code == 403
    assert client.get("/api/projects", headers={"Host": "example.com"}).status_code == 400
    assert client.post("/api/instances", json=payload, headers={"Origin": "http://localhost:5173"}).status_code == 201


def test_unique_order_and_running_edit_protection(client, runtime, demo):
    root = f"/api/projects/{demo['id']}"
    payload = {"order": 1, "title": "Duplicata", "prompt": "Outra descrição"}
    assert client.post(root + "/scenes", json=payload).json()["error"]["code"] == "duplicate_order"
    with runtime.db() as db, pytest.raises(IntegrityError):
        db.add(Scene(project_id=demo["id"], continuity="none", references=[], **payload))
        db.commit()
    assert client.post(root + "/run/start").status_code == 200
    assert client.post(root + "/scenes", json={**payload, "order": 4}).status_code == 409


def test_reorder_and_round_trip_json_markdown(client, demo):
    root = f"/api/projects/{demo['id']}"
    ordered = list(reversed([scene["id"] for scene in demo["scenes"]]))
    response = client.put(root + "/scenes/order", json={"scene_ids": ordered})
    assert [scene["id"] for scene in response.json()["scenes"]] == ordered
    manifest = client.get(root + "/export").json()
    md = client.get(root + "/export?format=markdown").text
    json_copy = client.post("/api/projects/import", json={"instance_id": demo["instance_id"], "manifest": manifest})
    md_copy = client.post("/api/projects/import-markdown", json={"instance_id": demo["instance_id"], "markdown": md})
    assert json_copy.status_code == 201, json_copy.text
    assert md_copy.status_code == 201, md_copy.text
    new = client.get(f"/api/projects/{md_copy.json()['id']}/export").json()
    assert new == manifest


def test_profile_isolation_registry_and_lock(client, runtime):
    ids = []
    for index in range(10):
        result = client.post("/api/instances", json={"name": f"Perfil {index + 1}", "provider": "flow"})
        assert result.status_code == 201
        ids.append(result.json()["id"])
    root = runtime.root / "browser_profiles"
    profiles = [BrowserInstanceManager.profile(root, identifier) for identifier in ids]
    assert len(set(profiles)) == 10 and not any(profile.exists() for profile in profiles)
    profiles[0].mkdir()
    other_manager = BrowserInstanceManager(root)
    try:
        with FileLock(profiles[0] / ".fabritake.lock"):
            result = other_manager.call("open", ids[0])
            assert result.availability == "blocked" and "em uso" in result.message
    finally:
        other_manager.shutdown()
    with pytest.raises(Timeout):
        Runtime(runtime.root)


def test_reference_upload_and_file_allowlist(client, demo, runtime):
    root = f"/api/projects/{demo['id']}"
    from app.infrastructure.providers import FakeVideoProvider
    payload = FakeVideoProvider.fixture(1, "png").read_bytes()
    upload = client.post(root + "/references", files={"file": ("diagrama.png", payload, "image/png")})
    assert upload.status_code == 201
    path = upload.json()["path"]
    assert client.get(root + "/files/" + path).content == payload
    project_path = runtime.root / "projects" / demo["slug"]
    (project_path / "edicao" / "private.txt").write_text("private")
    assert client.get(root + "/files/edicao/private.txt").status_code == 404
    assert client.get(root + "/files/%2e%2e%2fbrowser_profiles%2fx").status_code == 400
    first = demo["scenes"][0]
    data = {name: first[name] for name in ("order", "title", "prompt", "duration")}
    data.update(references=[path], continuity="explicit_reference")
    assert client.put(root + "/scenes/" + first["id"], json=data).status_code == 200


def test_real_mode_is_diagnostic_only(client, runtime, demo):
    instance = client.post("/api/instances", json={"name": "Flow", "provider": "flow"}).json()
    manifest = client.get(f"/api/projects/{demo['id']}/export").json()
    manifest["project"]["provider"] = "flow"
    project = client.post("/api/projects/import", json={"instance_id": instance["id"], "manifest": manifest}).json()
    path = f"/api/projects/{project['id']}"
    assert client.post(path + "/run/start").status_code == 200
    assert runtime.worker.step()
    actual = client.get(path).json()
    assert actual["status"] == "paused"
    assert actual["error"]["code"] == "provider_unverified"
    assert actual["scenes"][0]["attempts"][0]["evidence"] is None


def test_metadata_preserves_edited_markdown(client, demo, runtime):
    root = runtime.root / "projects" / demo["slug"]
    script = root / "roteiro.md"
    edited = script.read_bytes() + b"\nEdicao no Obsidian.\n"
    script.write_bytes(edited)
    project = client.get(f"/api/projects/{demo['id']}/export").json()["project"]
    project["title"] = "Título atualizado"
    response = client.put(f"/api/projects/{demo['id']}", json={**project, "instance_id": demo["instance_id"]})
    assert response.status_code == 200
    assert script.read_bytes() == edited
    assert "Título atualizado" in (root / "projeto.json").read_text(encoding="utf-8")


def test_imports_crlf_and_prompt_with_inline_fence(client, demo):
    manifest = client.get(f"/api/projects/{demo['id']}/export").json()
    manifest["scenes"][0]["prompt"] = "Uma linha.\n" + chr(96) * 4 + " seguido de texto.\nMais uma linha."
    from app.application.projects import render_script
    response = client.post("/api/projects/import-markdown", json={
        "markdown": render_script(manifest).replace("\n", "\r\n"), "instance_id": demo["instance_id"],
    })
    assert response.status_code == 201, response.text
    assert response.json()["scenes"][0]["prompt"] == manifest["scenes"][0]["prompt"]
