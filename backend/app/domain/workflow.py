from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol


TRANSITIONS = {
    "pending": {"preparing"},
    "preparing": {"submitting", "paused", "failed"},
    "submitting": {"generating", "requires_reconciliation"},
    "generating": {"saving_frame", "requires_reconciliation", "failed"},
    "saving_frame": {"downloading", "failed", "requires_reconciliation"},
    "downloading": {"validating", "failed", "requires_reconciliation"},
    "validating": {"awaiting_review", "completed", "failed", "requires_reconciliation"},
    "awaiting_review": {"completed", "failed"},
    "paused": {"pending"},
    "failed": {"pending"},
    "completed": {"pending"},
    "requires_reconciliation": {"failed", "validating", "generating"},
}


def transition(scene, target: str):
    if target not in TRANSITIONS[scene.state]:
        raise WorkflowError("invalid_transition", f"Transição inválida: {scene.state} → {target}.", 409)
    scene.state = target


class WorkflowError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code = code
        self.status = status

    def as_dict(self):
        return {"code": self.code, "message": str(self)}


@dataclass(frozen=True)
class ProviderStatus:
    auth: str
    availability: str
    credits: int | None = None
    credit_source: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class Generation:
    attempt_id: str
    project_id: str
    remote_project_id: str | None
    instance_id: str
    order: int
    prompt: str
    references: tuple[Path, ...]
    model: str | None
    ratio: str
    duration: int | None
    timeout: int
    paid_authorized: bool


@dataclass(frozen=True)
class Submission:
    remote_id: str | None
    evidence: str
    remote_project_id: str | None = None


class VideoGenerationProvider(Protocol):
    def status(self, instance_id: str) -> ProviderStatus: ...
    def prepare(self, request: Generation): ...
    def submit(self, request: Generation) -> Submission: ...
    def reconcile(self, instance_id: str, submission: Submission) -> bool: ...
    def wait(self, request: Generation, submission: Submission, stopping: Callable[[], bool]): ...
    def save_frame(self, request: Generation, submission: Submission, path: Path) -> str | None: ...
    def download(self, request: Generation, submission: Submission, path: Path): ...
