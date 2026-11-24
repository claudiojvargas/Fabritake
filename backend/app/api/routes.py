import hashlib
import os
import shutil
import subprocess
import sys
from typing import Literal

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy import select

from app.api.schemas import (
    ImportInput, InstanceInput, InstanceView, LogView, Manifest, MarkdownInput, OrderInput,
    ProjectDetail, ProjectInput, ProjectView, Reconciliation, Review, SceneDetail, SceneInput, SceneView,
)
from app.application.orchestration import observe
from app.application.projects import (
    ACTIVE, PROJECT_FIELDS, SCENE_FIELDS, ensure_idle, fields, get, history, parse_script, record, render_script, scenes,
)
from app.config import ROOT
from app.domain.workflow import WorkflowError
from app.infrastructure.artifacts import atomic_write, safe, slug
from app.infrastructure.database import Attempt, Instance, Log, Project, Scene, uid
from app.runtime import Runtime

router = APIRouter(prefix="/api")

PROJECT_VIEW = PROJECT_FIELDS + ("id", "slug", "status", "created_at", "updated_at", "remote_id", "error")
SCENE_VIEW = SCENE_FIELDS + ("id", "project_id", "state", "remote_id", "files", "dependencies", "selected_attempt", "stale", "error")
ATTEMPT_VIEW = ("id", "scene_id", "instance_id", "created_at", "updated_at", "state", "remote_id", "evidence", "files", "dependencies", "error")
INSTANCE_VIEW = ("id", "name", "provider", "auth", "availability", "credits", "credit_source", "checked_at", "error")
LOG_VIEW = ("id", "at", "project_id", "scene_id", "attempt_id", "instance_id", "event", "detail")


def runtime(request: Request) -> Runtime:
    return request.app.state.runtime


Local = Depends(runtime)


def scene_for(db, project_id, scene_id):
    scene = get(db, Scene, scene_id)
    if scene.project_id != project_id:
        raise WorkflowError("not_found", "Cena não encontrada neste projeto.", 404)
    return scene


def project_view(db, r, project, detail=False):
    ordered = scenes(db, project.id)
    view = fields(project, PROJECT_VIEW)
    view.update(total=len(ordered), completed=sum(scene.state == "completed" and not scene.stale for scene in ordered),
                folder=str(r.projects.store.folder(project)), instance_name=get(db, Instance, project.instance_id).name)
    if detail:
        view["scenes"] = [{**fields(scene, SCENE_VIEW), "attempts": [fields(attempt, ATTEMPT_VIEW)
                           for attempt in history(db, scene.id)]} for scene in ordered]
        view["references_available"] = reference_files(r, project)
    return view


def reference_files(r, project):
    root = r.projects.store.folder(project)
    return [path.relative_to(root).as_posix() for path in sorted(safe(root, "referencias").glob("*"))
            if path.is_file() and not path.is_symlink()]


def persist_metadata(db, r, project):
    db.commit()
    r.worker.sync_files(db, project)


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/projects", response_model=list[ProjectView], response_model_exclude_unset=True)
def list_projects(r: Runtime = Local):
    with r.db() as db:
        return [project_view(db, r, p) for p in db.scalars(select(Project).order_by(Project.created_at.desc()))]


@router.post("/projects", status_code=201, response_model=ProjectDetail, response_model_exclude_unset=True)
def create_project(data: ProjectInput, r: Runtime = Local):
    with r.write() as db:
        project = r.projects.create(db, data.model_dump())
        persist_metadata(db, r, project)
        return project_view(db, r, project, True)


def load_project(db, r, instance_id, manifest):
    for reference in manifest.project.references + [ref for scene in manifest.scenes for ref in scene.references]:
        r.projects.store.validate_reference_name(reference)
    metadata = manifest.project.model_dump()
    metadata["settings"]["paid_authorized"] = False
    project = r.projects.create(db, {**metadata, "instance_id": instance_id, "references": []})
    for item in manifest.scenes:
        # Manifests transfer metadata only; paths are retained for re-upload at the destination.
        payload = item.model_dump()
        scene = r.projects.save_scene(db, project, {**payload, "references": []})
        scene.references = payload["references"]
    project.references = manifest.project.references
    record(db, "manifest_imported", project)
    persist_metadata(db, r, project)
    return project_view(db, r, project, True)


@router.post("/projects/import", status_code=201, response_model=ProjectDetail, response_model_exclude_unset=True)
def import_project(data: ImportInput, r: Runtime = Local):
    with r.write() as db:
        return load_project(db, r, data.instance_id, data.manifest)


@router.post("/projects/import-markdown", status_code=201, response_model=ProjectDetail, response_model_exclude_unset=True)
def import_markdown(data: MarkdownInput, r: Runtime = Local):
    manifest = Manifest.model_validate(parse_script(data.markdown))
    with r.write() as db:
        return load_project(db, r, data.instance_id, manifest)


@router.post("/demo", status_code=201, response_model=ProjectDetail, response_model_exclude_unset=True)
def demo(r: Runtime = Local):
    manifest = Manifest.model_validate_json((ROOT / "examples" / "monolito-modular.json").read_text(encoding="utf-8"))
    with r.write() as db:
        instance = db.scalar(select(Instance).where(Instance.provider == "simulated").order_by(Instance.name))
        if instance is None:
            identifier = uid()
            instance = Instance(id=identifier, profile=f"browser_profiles/{identifier}",
                                name="Simulador local", provider="simulated")
            observe(instance, r.worker.providers["simulated"].status(identifier))
            db.add(instance)
            db.flush()
        return load_project(db, r, instance.id, manifest)


@router.get("/projects/{project_id}", response_model=ProjectDetail, response_model_exclude_unset=True)
def read_project(project_id: str, r: Runtime = Local):
    with r.db() as db:
        return project_view(db, r, get(db, Project, project_id), True)


@router.put("/projects/{project_id}", response_model=ProjectDetail, response_model_exclude_unset=True)
def update_project(project_id: str, data: ProjectInput, r: Runtime = Local):
    with r.write() as db:
        project = get(db, Project, project_id)
        r.projects.update(db, project, data.model_dump())
        persist_metadata(db, r, project)
        return project_view(db, r, project, True)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, r: Runtime = Local):
    with r.write() as db:
        project = get(db, Project, project_id)
        ensure_idle(project)
        if any(scene.state == "requires_reconciliation" for scene in scenes(db, project.id)):
            raise WorkflowError("unresolved_submission", "Resolva a submissão antes de remover o projeto.")
        db.delete(project)


@router.post("/projects/{project_id}/scenes", status_code=201, response_model=SceneView, response_model_exclude_unset=True)
def create_scene(project_id: str, data: SceneInput, r: Runtime = Local):
    with r.write() as db:
        project = get(db, Project, project_id)
        scene = r.projects.save_scene(db, project, data.model_dump())
        persist_metadata(db, r, project)
        return fields(scene, SCENE_VIEW)


@router.put("/projects/{project_id}/scenes/order", response_model=ProjectDetail, response_model_exclude_unset=True)
def reorder_scenes(project_id: str, data: OrderInput, r: Runtime = Local):
    with r.write() as db:
        project = get(db, Project, project_id)
        r.projects.reorder(db, project, data.scene_ids)
        persist_metadata(db, r, project)
        return project_view(db, r, project, True)


@router.get("/projects/{project_id}/scenes/{scene_id}", response_model=SceneDetail, response_model_exclude_unset=True)
def read_scene(project_id: str, scene_id: str, r: Runtime = Local):
    with r.db() as db:
        scene = scene_for(db, project_id, scene_id)
        return {**fields(scene, SCENE_VIEW), "attempts": [fields(item, ATTEMPT_VIEW) for item in history(db, scene.id)]}


@router.put("/projects/{project_id}/scenes/{scene_id}", response_model=SceneView, response_model_exclude_unset=True)
def update_scene(project_id: str, scene_id: str, data: SceneInput, r: Runtime = Local):
    with r.write() as db:
        project = get(db, Project, project_id)
        scene = r.projects.save_scene(db, project, data.model_dump(), scene_for(db, project_id, scene_id))
        persist_metadata(db, r, project)
        return fields(scene, SCENE_VIEW)


@router.delete("/projects/{project_id}/scenes/{scene_id}", status_code=204)
def delete_scene(project_id: str, scene_id: str, r: Runtime = Local):
    with r.write() as db:
        project = get(db, Project, project_id)
        ensure_idle(project)
        scene = scene_for(db, project_id, scene_id)
        ordered = scenes(db, project_id)
        if history(db, scene_id) or any(other.order > scene.order and history(db, other.id) for other in ordered):
            raise WorkflowError("history_locked", "Não é possível excluir uma cena com histórico ou anterior a um clipe já produzido.")
        db.delete(scene)
        record(db, "scene_removed", project, scene)
        persist_metadata(db, r, project)


@router.post("/projects/{project_id}/run/{action}")
def project_action(project_id: str, action: Literal["start", "pause", "resume"], r: Runtime = Local):
    with r.write() as db:
        project = get(db, Project, project_id)
        if action == "pause":
            if project.status in {"queued", "running"}:
                in_flight = any(s.state in {"preparing", "submitting", "generating", "saving_frame", "downloading", "validating"}
                                for s in scenes(db, project_id))
                project.status = "pausing" if in_flight else "paused"
                record(db, "pause_requested", project)
        else:
            r.worker.schedule(db, project)
        persist_metadata(db, r, project)
        return {"status": project.status}


@router.post("/projects/{project_id}/scenes/{scene_id}/retry")
def retry(project_id: str, scene_id: str, r: Runtime = Local):
    with r.write() as db:
        project = get(db, Project, project_id)
        r.worker.retry(db, project, scene_for(db, project_id, scene_id))
        persist_metadata(db, r, project)
        return {"status": project.status}


@router.post("/projects/{project_id}/scenes/{scene_id}/keep")
def keep(project_id: str, scene_id: str, r: Runtime = Local):
    with r.write() as db:
        project = get(db, Project, project_id)
        ensure_idle(project)
        scene = scene_for(db, project_id, scene_id)
        if not scene.stale or scene.state != "completed":
            raise WorkflowError("no_stale_artifact", "A cena não tem mídia desatualizada para confirmar.")
        scene.stale = False
        record(db, "previous_version_kept", project, scene)
        persist_metadata(db, r, project)
        return {"state": scene.state}


@router.post("/projects/{project_id}/scenes/{scene_id}/review")
def review(project_id: str, scene_id: str, data: Review, r: Runtime = Local):
    with r.write() as db:
        project = get(db, Project, project_id)
        scene = scene_for(db, project_id, scene_id)
        r.worker.review(db, project, scene, data.approve)
        return {"state": scene.state}


@router.post("/projects/{project_id}/scenes/{scene_id}/reconcile")
def reconcile(project_id: str, scene_id: str, data: Reconciliation, r: Runtime = Local):
    with r.write() as db:
        project = get(db, Project, project_id)
        scene = scene_for(db, project_id, scene_id)
        r.recovery.reconcile(db, project, scene, data.acknowledge)
        persist_metadata(db, r, project)
        return {"state": scene.state}


@router.get("/projects/{project_id}/export")
def export(project_id: str, format: Literal["json", "markdown"] = "json", r: Runtime = Local):
    with r.db() as db:
        project = get(db, Project, project_id)
        manifest = r.projects.manifest(db, project)
        if format == "markdown":
            return PlainTextResponse(render_script(manifest), headers={"Content-Disposition": 'attachment; filename="roteiro.md"'})
        return manifest


@router.post("/projects/{project_id}/references", status_code=201)
def upload_reference(project_id: str, file: UploadFile = File(...), r: Runtime = Local):
    data = file.file.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        raise WorkflowError("file_too_large", "A referência deve ter até 10 MB.", 413)
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        extension = "png"
    elif data.startswith(b"\xff\xd8\xff"):
        extension = "jpg"
    elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        extension = "webp"
    else:
        raise WorkflowError("invalid_image", "Envie uma imagem PNG, JPEG ou WebP.", 422)
    with r.write() as db:
        project = get(db, Project, project_id)
        ensure_idle(project)
        basename = (file.filename or "referencia").replace("\\", "/").rsplit("/", 1)[-1]
        stem = slug(basename.rsplit(".", 1)[0])
        root = r.projects.store.folder(project)
        pending = set(project.references)
        for scene in scenes(db, project_id):
            pending.update(scene.references)
        pending_match = f"referencias/{basename}"
        relative = f"referencias/{stem}-{hashlib.sha256(data).hexdigest()[:12]}.{extension}"
        uploaded_suffix = basename.rsplit(".", 1)[-1].lower()
        if pending_match in pending and (uploaded_suffix == extension or {uploaded_suffix, extension} == {"jpg", "jpeg"}):
            relative = pending_match
        r.projects.store.validate_reference_name(relative)
        path = safe(root, relative)
        if path.exists() and path.read_bytes() != data:
            raise WorkflowError("reference_conflict", "Já existe uma referência diferente com o mesmo nome.")
        if not path.exists():
            atomic_write(path, data)
        record(db, "reference_uploaded", project)
        return {"path": relative}


@router.get("/projects/{project_id}/files/{relative:path}")
def get_file(project_id: str, relative: str, download: bool = False, r: Runtime = Local):
    with r.db() as db:
        project = get(db, Project, project_id)
        root = r.projects.store.folder(project)
        path = safe(root, relative)
        name = path.name
        allowed = {"projeto.json", "roteiro.md", "prompts.md", "logs/eventos.jsonl", *reference_files(r, project)}
        for scene in scenes(db, project_id):
            for attempt in history(db, scene.id):
                for kind in ("video", "frame"):
                    archived = attempt.files.get(kind)
                    if archived:
                        allowed.add(archived)
                    if archived and relative == scene.files.get(kind) and attempt.id == scene.selected_attempt:
                        allowed.add(relative)
                        path = safe(root, archived)
        if relative not in allowed or not path.is_file():
            raise WorkflowError("file_not_found", "Arquivo indisponível.", 404)
        return FileResponse(path, filename=name if download else None, headers={"Cache-Control": "no-cache"})



@router.post("/projects/{project_id}/open-folder")
def open_folder(project_id: str, r: Runtime = Local):
    with r.db() as db:
        root = r.projects.store.folder(get(db, Project, project_id))
        if not root.is_dir():
            raise WorkflowError("folder_missing", "Pasta do projeto indisponível.")
        try:
            if sys.platform == "win32":
                os.startfile(str(root))
            else:
                opener = shutil.which("open" if sys.platform == "darwin" else "xdg-open")
                if not opener or (sys.platform.startswith("linux") and not (os.getenv("DISPLAY") or os.getenv("WAYLAND_DISPLAY"))):
                    raise OSError()
                subprocess.Popen([opener, str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            raise WorkflowError("folder_unavailable", "Não foi possível abrir a pasta nesta sessão gráfica.") from None
        return {"path": str(root)}


@router.get("/instances", response_model=list[InstanceView], response_model_exclude_unset=True)
def list_instances(r: Runtime = Local):
    with r.db() as db:
        return [fields(item, INSTANCE_VIEW) for item in db.scalars(select(Instance).order_by(Instance.name))]


@router.post("/instances", status_code=201, response_model=InstanceView, response_model_exclude_unset=True)
def create_instance(data: InstanceInput, r: Runtime = Local):
    with r.write() as db:
        identifier = uid()
        item = Instance(id=identifier, profile=f"browser_profiles/{identifier}", **data.model_dump())
        observe(item, r.worker.providers[item.provider].status(identifier))
        db.add(item)
        db.flush()
        return fields(item, INSTANCE_VIEW)


@router.post("/instances/{instance_id}/{action}", response_model=InstanceView, response_model_exclude_unset=True)
def instance_action(instance_id: str, action: Literal["open", "check", "close"], r: Runtime = Local):
    with r.write() as db:
        item = get(db, Instance, instance_id)
        if action == "check":
            result = r.worker.providers[item.provider].status(instance_id)
        elif item.provider == "simulated":
            raise WorkflowError("simulated_profile", "A instância simulada funciona sem navegador.")
        else:
            busy = db.scalar(select(Project.id).where(Project.instance_id == item.id, Project.status.in_(ACTIVE)))
            if busy:
                raise WorkflowError("profile_busy", "Pause o projeto vinculado antes de abrir ou fechar o perfil.")
            result = r.browser.call(action, instance_id)
        observe(item, result)
        db.add(Log(instance_id=item.id, event=f"instance_{action}", detail=result.availability))
        return fields(item, INSTANCE_VIEW)


@router.get("/logs", response_model=list[LogView], response_model_exclude_unset=True)
def logs(project_id: str | None = None, r: Runtime = Local):
    statement = select(Log).order_by(Log.id.desc()).limit(300)
    if project_id:
        statement = statement.where(Log.project_id == project_id)
    with r.db() as db:
        return [fields(item, LOG_VIEW) for item in db.scalars(statement)]
