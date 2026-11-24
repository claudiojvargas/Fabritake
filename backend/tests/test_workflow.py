from types import SimpleNamespace

import pytest

from app.application.projects import scenes
from app.domain.workflow import ProviderStatus, WorkflowError, transition
from app.infrastructure.artifacts import MediaValidator, safe
from app.infrastructure.database import Attempt, Project
from app.infrastructure.providers import FakeVideoProvider


def run(client, runtime, project):
    response = client.post(f"/api/projects/{project['id']}/run/start")
    assert response.status_code == 200, response.text
    for _ in range(len(project["scenes"]) + 2):
        if not runtime.worker.step():
            break
    return read(client, project)


def read(client, project):
    return client.get(f"/api/projects/{project['id']}").json()


def test_invalid_transition():
    scene = SimpleNamespace(state="pending")
    with pytest.raises(WorkflowError, match="Transição inválida"):
        transition(scene, "completed")
    assert scene.state == "pending"


def test_three_clips_in_order_with_continuity(client, runtime, demo):
    project = run(client, runtime, demo)
    assert project["status"] == "completed"
    first, second, third = project["scenes"]
    assert first["attempts"][0]["dependencies"] == []
    assert second["attempts"][0]["dependencies"] == [{"scene_id": first["id"], "attempt_id": first["selected_attempt"]}]
    assert third["attempts"][0]["dependencies"] == [{"scene_id": second["id"], "attempt_id": second["selected_attempt"]}]
    for index, scene in enumerate(project["scenes"], 1):
        assert scene["files"]["video"].startswith(f"videos/{index:02d}-")
        assert scene["files"]["frame_source"] == "fixture"
        response = client.get(f"/api/projects/{project['id']}/files/{scene['files']['video']}", headers={"Range": "bytes=0-11"})
        assert response.status_code == 206
        assert response.content[4:8] == b"ftyp"
    assert (runtime.root / "projects" / project["slug"] / "projeto.json").is_file()


def test_regeneration_keeps_variants_and_flags_dependents(client, runtime, demo):
    project = run(client, runtime, demo)
    original = project["scenes"][0]
    endpoint = f"/api/projects/{project['id']}/scenes/{original['id']}"
    assert client.post(endpoint + "/retry").status_code == 200
    project = run(client, runtime, demo)
    first, second, third = project["scenes"]
    assert [first["stale"], second["stale"], third["stale"]] == [False, True, True]
    assert first["selected_attempt"] != original["selected_attempt"]
    assert len(first["attempts"]) == 2
    assert project["status"] == "paused"
    for dependent in (second, third):
        response = client.post(f"/api/projects/{project['id']}/scenes/{dependent['id']}/keep")
        assert response.status_code == 200
    assert run(client, runtime, demo)["status"] == "completed"


def test_review_gates_next_scene(client, runtime, demo):
    meta = client.get(f"/api/projects/{demo['id']}/export").json()["project"]
    meta["settings"]["manual_review"] = True
    assert client.put(f"/api/projects/{demo['id']}", json={**meta, "instance_id": demo["instance_id"]}).status_code == 200
    project = run(client, runtime, demo)
    first, second, _ = project["scenes"]
    assert first["state"] == "awaiting_review" and second["state"] == "pending"
    assert not first["files"] and first["attempts"][0]["files"]["video"]
    assert client.post(f"/api/projects/{demo['id']}/run/resume").status_code == 409
    assert client.post(f"/api/projects/{demo['id']}/scenes/{first['id']}/review", json={"approve": True}).status_code == 200
    assert run(client, runtime, demo)["scenes"][1]["state"] == "awaiting_review"


@pytest.mark.parametrize(("status", "code"), [
    (ProviderStatus("simulated", "available", 0, "stub"), "quota"),
    (ProviderStatus("expired", "manual"), "login_required"),
])
def test_provider_pause_and_resume(client, runtime, demo, monkeypatch, status, code):
    provider = runtime.worker.providers["simulated"]
    with monkeypatch.context() as patch:
        patch.setattr(provider, "status", lambda _: status)
        project = run(client, runtime, demo)
    assert project["status"] == "paused"
    assert project["error"]["code"] == code
    assert project["scenes"][0]["attempts"][0]["remote_id"] is None
    assert run(client, runtime, demo)["status"] == "completed"


def test_download_failure_retains_attempt(client, runtime, demo, monkeypatch):
    def unavailable(*_):
        raise WorkflowError("download_error", "Download interrompido.")
    monkeypatch.setattr(runtime.worker.providers["simulated"], "download", unavailable)
    project = run(client, runtime, demo)
    attempt = project["scenes"][0]["attempts"][0]
    assert attempt["state"] == "failed" and attempt["error"]["code"] == "download_error"
    assert attempt["remote_id"].startswith("sim-")
    assert not attempt["files"]


def test_invalid_media_is_rejected(tmp_path, monkeypatch):
    media = MediaValidator()
    monkeypatch.setattr(media, "ffmpeg", None)
    monkeypatch.setattr(media, "ffprobe", None)
    fixture = FakeVideoProvider.fixture(1, "mp4")
    media.validate(fixture, "video", "1.mp4")
    invalid = tmp_path / "bad.mp4"
    invalid.write_bytes(fixture.read_bytes()[:20])
    with pytest.raises(WorkflowError, match="fixture"):
        media.validate(invalid, "video", "1.mp4")
    with pytest.raises(WorkflowError, match="FFmpeg"):
        media.validate(fixture, "video")


def test_intent_survives_restart_without_duplicate(tmp_path):
    from app.runtime import Runtime
    from app.api.routes import load_project
    from app.api.schemas import Manifest
    from app.config import ROOT
    from app.infrastructure.database import Instance

    root = tmp_path / "recovery"
    runtime = Runtime(root)
    try:
        with runtime.write() as db:
            instance = Instance(name="Crash", provider="simulated", profile="isolated")
            db.add(instance)
            db.flush()
            manifest = Manifest.model_validate_json((ROOT / "examples/monolito-modular.json").read_text())
            project = load_project(db, runtime, instance.id, manifest)
            first = scenes(db, project["id"])[0]
            db.get(Project, project["id"]).status = "running"
            first.state = "submitting"
            db.add(Attempt(scene_id=first.id, instance_id=instance.id, state="submitting"))
    finally:
        runtime.close()
    restarted = Runtime(root)
    try:
        with restarted.db() as db:
            restored = db.get(Project, project["id"])
            first = scenes(db, restored.id)[0]
            assert restored.status == "paused"
            assert first.state == "requires_reconciliation"
            with pytest.raises(WorkflowError):
                restarted.worker.schedule(db, restored)
            with pytest.raises(WorkflowError):
                restarted.worker.retry(db, restored, first)
        assert not restarted.worker.step()
    finally:
        restarted.close()


def test_recovery_existing_archive_without_resubmission(client, runtime, demo, monkeypatch):
    original = runtime.worker.select
    def interrupted(*_):
        raise OSError("interrupted promotion")
    with monkeypatch.context() as patch:
        patch.setattr(runtime.worker, "select", interrupted)
        project = run(client, runtime, demo)
    first = project["scenes"][0]
    assert first["state"] == "requires_reconciliation"
    assert runtime.worker.select == original
    submit = []
    monkeypatch.setattr(runtime.worker.providers["simulated"], "submit", lambda *_: submit.append(1))
    response = client.post(f"/api/projects/{demo['id']}/scenes/{first['id']}/reconcile", json={})
    assert response.status_code == 200 and response.json()["state"] == "completed"
    assert not submit and len(read(client, demo)["scenes"][0]["attempts"]) == 1


def test_path_traversal_and_symlinks(tmp_path):
    (tmp_path / "link").symlink_to(tmp_path.parent, target_is_directory=True)
    for relative in ["../database/private", "link/private", "/etc/passwd", "x\\..\\secret", "C:/Users/user"]:
        with pytest.raises(WorkflowError):
            safe(tmp_path, relative)


def test_pause_while_waiting_prevents_further_submissions(client, runtime, demo, monkeypatch):
    submitted = []
    provider = runtime.worker.providers["simulated"]
    submit = provider.submit
    def pause(request, receipt, stopping):
        assert client.post(f"/api/projects/{demo['id']}/run/pause").json()["status"] == "pausing"
    def capture(request):
        submitted.append(request.order)
        return submit(request)
    monkeypatch.setattr(provider, "wait", pause)
    monkeypatch.setattr(provider, "submit", capture)
    project = run(client, runtime, demo)
    assert project["status"] == "paused"
    assert submitted == [1]
    assert [scene["state"] for scene in project["scenes"]] == ["completed", "pending", "pending"]


def test_ffmpeg_extracts_decodable_last_frame(tmp_path):
    media = MediaValidator()
    if not media.ffmpeg or not media.ffprobe:
        pytest.skip("FFmpeg e FFprobe indisponíveis.")
    frame = tmp_path / "frame.png"
    assert media.extract(FakeVideoProvider.fixture(2, "mp4"), frame) == "ffmpeg"
    media.validate(frame, "frame")
    assert frame.read_bytes() == FakeVideoProvider.fixture(2, "png").read_bytes()
