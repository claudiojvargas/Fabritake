import json
import re

from sqlalchemy import func, select

from app.domain.workflow import WorkflowError
from app.infrastructure.artifacts import atomic_write, safe, slug
from app.infrastructure.database import Attempt, Instance, Log, Project, Scene, uid


ACTIVE = {"queued", "running", "pausing"}
BLOCKING = {"submitting", "generating", "saving_frame", "downloading", "validating", "requires_reconciliation"}
PROJECT_FIELDS = ("title", "description", "language", "duration", "ratio", "provider", "instance_id", "settings", "references")
SCENE_FIELDS = ("title", "prompt", "duration", "order", "references", "continuity")


def get(db, model, identifier):
    obj = db.get(model, identifier)
    if obj is None:
        raise WorkflowError("not_found", "Registro não encontrado.", 404)
    return obj


def fields(obj, names):
    return {key: getattr(obj, key) for key in names}


def scenes(db, project_id):
    return list(db.scalars(select(Scene).where(Scene.project_id == project_id).order_by(Scene.order)))


def history(db, scene_id):
    return list(db.scalars(select(Attempt).where(Attempt.scene_id == scene_id).order_by(Attempt.created_at.desc())))


def record(db, event, project, scene=None, attempt=None, detail=None):
    db.add(Log(event=event, project_id=project.id, instance_id=project.instance_id,
               scene_id=scene.id if scene else None, attempt_id=attempt.id if attempt else None, detail=detail))


def ensure_idle(project):
    if project.status in ACTIVE:
        raise WorkflowError("project_busy", "Pause o projeto e aguarde a cena atual para fazer alterações.")


class ProjectService:
    def __init__(self, store):
        self.store = store

    def create(self, db, data):
        self.check_instance(db, data["instance_id"], data["provider"])
        if data["references"]:
            raise WorkflowError("upload_first", "Crie o projeto antes de cadastrar referências.", 422)
        next_number = (db.scalar(select(func.count()).select_from(Project)) or 0) + 1
        while True:
            candidate = f"{next_number:03d}-{slug(data['title'])}"
            if not (self.store.root / candidate).exists() and not db.scalar(select(Project.id).where(Project.slug == candidate)):
                break
            next_number += 1
        project = Project(id=uid(), slug=candidate, **data)
        db.add(project)
        db.flush()
        self.store.initialize(project)
        record(db, "project_created", project)
        return project

    @staticmethod
    def check_instance(db, instance_id, provider):
        if get(db, Instance, instance_id).provider != provider:
            raise WorkflowError("instance_provider", "Selecione uma instância do mesmo provedor.", 422)

    def update(self, db, project, data):
        ensure_idle(project)
        self.check_instance(db, data["instance_id"], data["provider"])
        for reference in data["references"]:
            self.store.reference(project, reference)
        if (data["provider"], data["instance_id"]) != (project.provider, project.instance_id):
            if any(history(db, s.id) for s in scenes(db, project.id)):
                raise WorkflowError("binding_locked", "O vínculo com a instância fica fixo após a primeira tentativa.")
        for name, value in data.items():
            setattr(project, name, value)
        record(db, "project_updated", project)

    def save_scene(self, db, project, data, scene=None):
        ensure_idle(project)
        existing = scenes(db, project.id)
        other = next((item for item in existing if item.order == data["order"] and (scene is None or item.id != scene.id)), None)
        if other:
            raise WorkflowError("duplicate_order", "Já existe uma cena nessa posição.")
        produced = any(item.selected_attempt or item.state in BLOCKING or item.state == "awaiting_review" for item in existing)
        if produced and (scene is None or scene.order != data["order"]):
            highest = max(item.order for item in existing)
            if data["order"] <= highest or scene is not None:
                raise WorkflowError("order_locked", "Após gerar mídia, novas cenas precisam ser acrescentadas ao final.")
        for reference in data["references"]:
            self.store.reference(project, reference)
        if scene is None:
            scene = Scene(project_id=project.id, **data)
            db.add(scene)
            if project.status == "completed":
                project.status = "draft"
        else:
            if scene.state in BLOCKING or scene.state == "awaiting_review":
                raise WorkflowError("scene_locked", "Resolva a tentativa atual antes de editar a cena.")
            if history(db, scene.id) and data["title"] != scene.title:
                raise WorkflowError("title_locked", "O título da cena fica fixo após a primeira tentativa para preservar o nome dos arquivos.")
            for name, value in data.items():
                setattr(scene, name, value)
        db.flush()
        record(db, "scene_saved", project, scene)
        return scene

    def reorder(self, db, project, order):
        ensure_idle(project)
        current = scenes(db, project.id)
        lookup = {scene.id: scene for scene in current}
        if set(order) != set(lookup) or len(order) != len(current):
            raise WorkflowError("invalid_order", "Informe cada cena exatamente uma vez.", 422)
        if any(history(db, scene.id) for scene in current):
            raise WorkflowError("order_locked", "A ordenação fica fixa após a primeira tentativa.")
        for index, scene in enumerate(current, 1):
            scene.order = -index
        db.flush()
        for index, identifier in enumerate(order, 1):
            lookup[identifier].order = index
        record(db, "scenes_reordered", project)

    def manifest(self, db, project):
        data = fields(project, PROJECT_FIELDS)
        data.pop("instance_id")
        return {"version": 1, "project": data,
                "scenes": [fields(scene, SCENE_FIELDS) for scene in scenes(db, project.id)]}

    def export(self, db, project):
        root = self.store.folder(project)
        manifest = self.manifest(db, project)
        manifest["progress"] = {
            "project_id": project.id, "slug": project.slug, "status": project.status,
            "scenes": [fields(scene, ("id", "order", "state", "files", "stale", "selected_attempt"))
                       for scene in scenes(db, project.id)],
        }
        manifest_path = safe(root, "projeto.json")
        previous = None
        if manifest_path.is_file():
            try:
                previous = json.loads(manifest_path.read_text(encoding="utf-8"))
                if not isinstance(previous, dict) or "project" not in previous or "scenes" not in previous:
                    previous = None
            except (ValueError, OSError):
                pass
        for name, render in (("roteiro.md", render_script), ("prompts.md", render_prompts)):
            path = safe(root, name)
            content = render(manifest).encode()
            if not path.exists():
                atomic_write(path, content)
                continue
            if previous:
                try:
                    previous_content = render(previous).encode()
                except (KeyError, TypeError, ValueError):
                    continue
                if path.read_bytes() == previous_content and previous_content != content:
                    atomic_write(path, content)
        atomic_write(manifest_path, (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode())
        events = db.scalars(select(Log).where(Log.project_id == project.id).order_by(Log.id))
        log = "\n".join(json.dumps(fields(event, (
            "id", "at", "event", "project_id", "scene_id", "attempt_id", "instance_id", "detail",
        )), ensure_ascii=False) for event in events)
        atomic_write(safe(root, "logs/eventos.jsonl"), (log + "\n").encode())
        return manifest


def render_prompts(manifest):
    prompts = "\n\n".join(f"## {scene['order']:02d} · {scene['title']}\n\n{scene['prompt']}" for scene in manifest["scenes"])
    return f"# Prompts\n\n{prompts}\n"


def render_script(manifest):
    fence = chr(96) * 4
    project = manifest["project"]
    meta = json.dumps(project, indent=2, ensure_ascii=False)
    sections = []
    for scene in manifest["scenes"]:
        config = {name: value for name, value in scene.items() if name != "prompt"}
        sections.append(f"## Cena\n\n{fence}json\n"
                        + json.dumps(config, ensure_ascii=False, indent=2)
                        + f"\n{fence}\n\n{fence}prompt\n{scene['prompt']}\n{fence}\n")
    return f"# Fabritake v1\n\n{fence}json\n{meta}\n{fence}\n\n" + "\n".join(sections)


def parse_script(text):
    text = text.replace("\r\n", "\n")
    header = re.match(r"\s*# Fabritake v1\s*\n+`{4}json\n(.*?)\n`{4}\s*", text, re.S)
    scene = re.compile(r"## Cena\s*\n+`{4}json\n(.*?)\n`{4}\s*\n+`{4}prompt\n(.*?)\n`{4}(?=[ \t]*(?:\n|$))\s*", re.S)
    try:
        if not header:
            raise ValueError()
        project = json.loads(header[1])
        position = header.end()
        entries = []
        while position < len(text):
            section = scene.match(text, position)
            if not section:
                raise ValueError()
            entries.append(dict(json.loads(section[1]), prompt=section[2]))
            position = section.end()
        return {"version": 1, "project": project, "scenes": entries}
    except (ValueError, TypeError):
        raise WorkflowError("invalid_markdown", "O roteiro precisa seguir o formato Fabritake v1 documentado.", 422) from None
