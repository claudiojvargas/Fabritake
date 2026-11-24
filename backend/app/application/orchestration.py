import json
import logging
import shutil

from sqlalchemy import select

from app.application.projects import ACTIVE, BLOCKING, ensure_idle, get, history, record, scenes
from app.domain.workflow import Generation, Submission, WorkflowError, transition
from app.infrastructure.artifacts import atomic_write, safe
from app.infrastructure.database import Attempt, Instance, Project, Scene, now, uid

logger = logging.getLogger(__name__)
MANUAL_ERRORS = {"quota", "login_required", "captcha", "restricted", "provider_unverified", "provider_unavailable"}


def observe(instance, result):
    instance.auth = result.auth
    instance.availability = result.availability
    instance.credits = result.credits
    instance.credit_source = result.credit_source
    instance.checked_at = now()
    instance.error = result.message


class SceneOrchestrator:
    def __init__(self, db, lock, projects, media, providers, stopping):
        self.db = db
        self.lock = lock
        self.projects = projects
        self.store = projects.store
        self.media = media
        self.providers = providers
        self.stopping = stopping

    def sync_files(self, db, project):
        try:
            self.projects.export(db, project)
        except (WorkflowError, OSError):
            logger.warning("project_export_failed project_id=%s", project.id)

    def schedule(self, db, project):
        ensure_idle(project)
        ordered = scenes(db, project.id)
        if not ordered:
            raise WorkflowError("no_scenes", "Adicione pelo menos uma cena.")
        first = next((scene for scene in ordered if scene.state != "completed" or scene.stale), None)
        if first is None:
            project.status = "completed"
            project.error = None
            return
        if first.stale or first.state not in {"pending", "paused"}:
            raise WorkflowError("scene_blocking", "Resolva a próxima cena antes de retomar.")
        if first.state == "paused":
            transition(first, "pending")
        project.status = "queued"
        project.error = None
        record(db, "project_queued", project)

    def step(self):
        with self.lock, self.db() as db:
            project = db.scalar(select(Project).where(Project.status.in_({"queued", "running"}))
                                .order_by((Project.status == "running").desc(), Project.updated_at, Project.id))
            if project is None:
                return False
            ordered = scenes(db, project.id)
            index = next((i for i, scene in enumerate(ordered) if scene.state != "completed" or scene.stale), None)
            if index is None:
                project.status = "completed"
                record(db, "project_completed", project)
                db.commit()
                self.sync_files(db, project)
                return True
            scene = ordered[index]
            if scene.state != "pending" or scene.stale:
                project.status = "paused"
                record(db, "project_paused", project, scene)
                db.commit()
                self.sync_files(db, project)
                return True
            project.status = "running"
            scene.error = None
            transition(scene, "preparing")
            attempt = Attempt(id=uid(), scene_id=scene.id, instance_id=project.instance_id, state="preparing")
            db.add(attempt)
            record(db, "preparing", project, scene, attempt)
            db.commit()
            identifiers = (project.id, scene.id, attempt.id)
        self.execute(*identifiers)
        return True

    def request(self, db, project, scene, attempt):
        ordered = scenes(db, project.id)
        index = next(i for i, other in enumerate(ordered) if other.id == scene.id)
        references = [self.store.reference(project, ref) for ref in dict.fromkeys(project.references + scene.references)]
        dependencies = []
        if scene.continuity == "explicit_reference" and not scene.references:
            raise WorkflowError("missing_reference", "Adicione uma referência específica nesta cena.")
        if scene.continuity == "previous_final_frame" and index > 0:
            previous = ordered[index - 1]
            if previous.state != "completed" or previous.stale or not previous.files.get("frame"):
                raise WorkflowError("continuity_unresolved", "O frame anterior precisa estar aprovado e atualizado.")
            approved = get(db, Attempt, previous.selected_attempt)
            references.append(safe(self.store.folder(project), approved.files["frame"]))
            dependencies.append({"scene_id": previous.id, "attempt_id": previous.selected_attempt})
        attempt.dependencies = dependencies
        return Generation(
            attempt.id, project.id, project.remote_id, project.instance_id, scene.order, scene.prompt,
            tuple(references), project.settings.get("model"), project.ratio, scene.duration,
            project.settings["timeout"], project.settings["paid_authorized"],
        )

    def phase(self, db, project, scene, attempt, state, detail=None):
        transition(scene, state)
        attempt.state = state
        record(db, state, project, scene, attempt, detail)
        db.commit()

    def execute(self, project_id, scene_id, attempt_id):
        with self.db() as db:
            project = get(db, Project, project_id)
            scene = get(db, Scene, scene_id)
            attempt = get(db, Attempt, attempt_id)
            provider = self.providers[project.provider]
            submitted = False
            try:
                request = self.request(db, project, scene, attempt)
                observed = provider.status(project.instance_id)
                with self.lock:
                    observe(get(db, Instance, project.instance_id), observed)
                    db.commit()
                if observed.auth in {"manual_login", "expired"}:
                    raise WorkflowError("login_required", "Autentique-se manualmente na instância vinculada.")
                if observed.credits == 0:
                    raise WorkflowError("quota", "A instância vinculada está sem créditos observados.")
                if project.provider == "flow" and not request.paid_authorized:
                    raise WorkflowError("provider_unverified", "O Flow está em diagnóstico. Nenhuma geração foi enviada.")
                if observed.availability != "available":
                    raise WorkflowError("provider_unavailable", observed.message or "Provedor indisponível.")
                provider.prepare(request)
                with self.lock:
                    db.refresh(project)
                    if project.status == "pausing" or self.stopping():
                        raise WorkflowError("user_paused", "Pausa antes da submissão.")
                    self.phase(db, project, scene, attempt, "submitting")
                    submitted = True
                receipt = provider.submit(request)
                with self.lock:
                    attempt.remote_id = scene.remote_id = receipt.remote_id
                    attempt.evidence = receipt.evidence
                    if receipt.remote_project_id:
                        project.remote_id = receipt.remote_project_id
                    self.phase(db, project, scene, attempt, "generating")
                self.collect(db, project, scene, attempt, provider, request, receipt)
            except Exception as exc:
                db.rollback()
                error = exc if isinstance(exc, WorkflowError) else WorkflowError("workflow_error", "Falha local durante a execução.")
                if not isinstance(exc, WorkflowError):
                    logger.error("workflow_error project_id=%s scene_id=%s attempt_id=%s type=%s",
                                 project.id, scene.id, attempt.id, type(exc).__name__)
                with self.lock:
                    if scene.state == "preparing":
                        target = "paused" if error.code in MANUAL_ERRORS | {"user_paused"} else "failed"
                    elif project.provider == "simulated" and submitted and scene.state in {"saving_frame", "downloading", "validating"}:
                        target = "failed" if not self.store.attempt_directory(project, scene, attempt).is_dir() else "requires_reconciliation"
                    else:
                        target = "requires_reconciliation"
                    project.status = "paused"
                    project.error = scene.error = attempt.error = error.as_dict()
                    if scene.state in BLOCKING | {"preparing"}:
                        self.phase(db, project, scene, attempt, target, error.code)
                    else:
                        db.commit()
                    self.sync_files(db, project)

    def collect(self, db, project, scene, attempt, provider, request, receipt):
        provider.wait(request, receipt, self.stopping)
        directory = self.store.attempt_directory(project, scene, attempt)
        directory.parent.mkdir(parents=True, exist_ok=True)
        stage = directory.with_name(f".partial-{attempt.id}")
        stage.mkdir()
        video, frame = stage / "clipe.mp4", stage / "frame.png"
        try:
            with self.lock:
                self.phase(db, project, scene, attempt, "saving_frame")
            source = provider.save_frame(request, receipt, frame)
            with self.lock:
                self.phase(db, project, scene, attempt, "downloading")
            provider.download(request, receipt, video)
            with self.lock:
                self.phase(db, project, scene, attempt, "validating")
            self.media.validate(video, "video", self.fixture(project, scene, "mp4"))
            if source is None:
                source = self.media.extract(video, frame)
            self.media.validate(frame, "frame", self.fixture(project, scene, "png") if source == "fixture" else None)
            atomic_write(stage / "resultado.json", json.dumps({"frame_source": source}).encode())
            stage.rename(directory)
        except BaseException:
            if project.provider == "simulated":
                shutil.rmtree(stage, ignore_errors=True)
            raise
        with self.lock:
            self.finalize(db, project, scene, attempt)

    @staticmethod
    def fixture(project, scene, extension):
        return f"{(scene.order - 1) % 3 + 1}.{extension}" if project.provider == "simulated" else None

    def finalize(self, db, project, scene, attempt):
        directory = self.store.attempt_directory(project, scene, attempt)
        root = self.store.folder(project)
        result = json.loads(safe(directory, "resultado.json").read_text(encoding="utf-8"))
        attempt.files = {
            "video": (directory / "clipe.mp4").relative_to(root).as_posix(),
            "frame": (directory / "frame.png").relative_to(root).as_posix(),
            "frame_source": result["frame_source"],
        }
        db.refresh(project)
        project.error = scene.error = attempt.error = None
        if project.settings.get("manual_review"):
            project.status = "paused"
            self.phase(db, project, scene, attempt, "awaiting_review")
        else:
            self.select(db, project, scene, attempt)
            if project.status == "pausing" or self.stopping():
                project.status = "paused"
            elif all(other.state == "completed" and not other.stale for other in scenes(db, project.id)):
                project.status = "completed"
                record(db, "project_completed", project)
            self.phase(db, project, scene, attempt, "completed")
        self.sync_files(db, project)

    def select(self, db, project, scene, attempt):
        old = scene.selected_attempt
        old_files = get(db, Attempt, old).files if old else {}
        scene.files = self.store.select(project, scene, attempt, old_files)
        scene.selected_attempt = attempt.id
        scene.dependencies = attempt.dependencies
        scene.stale = False
        if old and old != attempt.id:
            stale_ids = {scene.id}
            for dependent in scenes(db, project.id):
                if any(dep["scene_id"] in stale_ids for dep in dependent.dependencies):
                    dependent.stale = True
                    stale_ids.add(dependent.id)
                    record(db, "continuity_stale", project, dependent)

    def review(self, db, project, scene, approve):
        ensure_idle(project)
        if scene.state != "awaiting_review":
            raise WorkflowError("no_review", "A cena não tem tentativa aguardando revisão.")
        attempt = history(db, scene.id)[0]
        if approve:
            self.select(db, project, scene, attempt)
            project.status = "completed" if all(
                other.id == scene.id or (other.state == "completed" and not other.stale)
                for other in scenes(db, project.id)
            ) else "paused"
            self.phase(db, project, scene, attempt, "completed", "manual_approval")
        else:
            if (self.store.attempt_directory(project, scene, attempt) / "selecao.json").exists():
                raise WorkflowError("selection_in_progress", "A aprovação já foi iniciada. Conclua a seleção dos arquivos.")
            scene.error = attempt.error = {"code": "rejected", "message": "Tentativa rejeitada na revisão."}
            self.phase(db, project, scene, attempt, "failed", "manual_rejection")
        self.sync_files(db, project)

    def retry(self, db, project, scene):
        ensure_idle(project)
        if scene.state not in {"failed", "completed", "paused"}:
            raise WorkflowError("retry_blocked", "Resolva a tentativa em aberto antes de solicitar outra.")
        transition(scene, "pending")
        scene.stale = False
        scene.error = None
        project.status = "paused"
        record(db, "retry_requested", project, scene)


class RecoveryService:
    def __init__(self, worker):
        self.worker = worker

    def recover(self):
        with self.worker.lock, self.worker.db() as db:
            for project in db.scalars(select(Project).where(Project.status.in_(ACTIVE))):
                if project.status != "queued":
                    project.status = "paused"
                for scene in scenes(db, project.id):
                    if scene.state not in BLOCKING | {"preparing"}:
                        continue
                    attempt = history(db, scene.id)[0]
                    self.recover_attempt(db, project, scene, attempt)
                db.commit()
                self.worker.sync_files(db, project)

    def recover_attempt(self, db, project, scene, attempt):
        directory = self.worker.store.attempt_directory(project, scene, attempt)
        if scene.state == "preparing":
            self.worker.phase(db, project, scene, attempt, "paused", "restart_before_submission")
            return
        if directory.is_dir() and scene.state in {"validating", "requires_reconciliation"}:
            try:
                for kind, extension, filename in (("video", "mp4", "clipe.mp4"), ("frame", "png", "frame.png")):
                    self.worker.media.validate(safe(directory, filename), kind, self.worker.fixture(project, scene, extension))
                if scene.state == "requires_reconciliation":
                    self.worker.phase(db, project, scene, attempt, "validating", "local_archive_found")
                self.worker.finalize(db, project, scene, attempt)
                return
            except (WorkflowError, OSError, ValueError, KeyError, TypeError):
                db.rollback()
        if scene.state != "requires_reconciliation":
            scene.error = attempt.error = {"code": "submission_unknown", "message": "Confira o resultado antes de solicitar nova tentativa."}
            self.worker.phase(db, project, scene, attempt, "requires_reconciliation", "restart_after_intent")
        partial = directory.with_name(f".partial-{attempt.id}")
        if partial.is_dir():
            record(db, "partial_download_retained", project, scene, attempt)

    def reconcile(self, db, project, scene, acknowledge):
        ensure_idle(project)
        if scene.state != "requires_reconciliation":
            raise WorkflowError("no_reconciliation", "Esta cena não está aguardando reconciliação.")
        attempt = history(db, scene.id)[0]
        self.recover_attempt(db, project, scene, attempt)
        if scene.state != "requires_reconciliation":
            return
        receipt = Submission(attempt.remote_id, attempt.evidence or "")
        if self.worker.providers[project.provider].reconcile(project.instance_id, receipt) and project.provider == "simulated":
            # Deterministic fixture recovery uses the same attempt and never calls submit.
            request = self.worker.request(db, project, scene, attempt)
            directory = self.worker.store.attempt_directory(project, scene, attempt)
            if directory.exists():
                raise WorkflowError("archive_conflict", "Revise o arquivo da tentativa no disco.")
            partial = directory.with_name(f".partial-{attempt.id}")
            shutil.rmtree(partial, ignore_errors=True)
            self.worker.phase(db, project, scene, attempt, "generating", "confirmed_fixture_receipt")
            try:
                self.worker.collect(db, project, scene, attempt, self.worker.providers[project.provider], request, receipt)
            except (WorkflowError, OSError):
                db.rollback()
                scene.error = attempt.error = {"code": "recovery_failed", "message": "A coleta da tentativa falhou."}
                self.worker.phase(db, project, scene, attempt, "requires_reconciliation")
            return
        if not acknowledge:
            raise WorkflowError("remote_unknown", "Verifique o provedor manualmente e confirme antes de encerrar a tentativa.")
        scene.error = attempt.error = {"code": "manually_closed", "message": "Submissão incerta encerrada após verificação manual."}
        self.worker.phase(db, project, scene, attempt, "failed", "manual_reconciliation")
