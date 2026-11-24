from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Identifier = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]
Duration = Annotated[int, Field(ge=1, le=86400)]
Provider = Literal["simulated", "flow"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Settings(Input):
    model: Name | None = None
    timeout: int = Field(ge=10, le=3600, default=300)
    manual_review: bool = False
    paid_authorized: bool = False


class ProjectMetadata(Input):
    title: Name
    description: str = Field(default="", max_length=8000)
    language: str = Field(default="pt-BR", pattern=r"^[a-z]{2,3}(?:-[a-zA-Z0-9]{2,8}){0,3}$")
    duration: Duration | None = None
    ratio: Literal["16:9", "9:16", "1:1"] = "16:9"
    provider: Provider = "simulated"
    settings: Settings = Field(default_factory=Settings)
    references: list[str] = Field(default_factory=list, max_length=40)


class ProjectInput(ProjectMetadata):
    instance_id: Identifier


class SceneInput(Input):
    order: int = Field(ge=1, le=9999)
    title: Name
    prompt: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=16000)]
    duration: Duration | None = None
    references: list[str] = Field(default_factory=list, max_length=40)
    continuity: Literal["none", "previous_final_frame", "explicit_reference"] = "previous_final_frame"

    @field_validator("prompt")
    @classmethod
    def compatible_markdown(cls, value):
        if chr(96) * 4 in value.splitlines():
            raise ValueError("Uma linha do prompt coincide com o delimitador reservado do roteiro.")
        return value


class InstanceInput(Input):
    name: Name
    provider: Provider


class Manifest(Input):
    version: Literal[1]
    project: ProjectMetadata
    scenes: list[SceneInput] = Field(max_length=999)
    progress: dict | None = None

    @model_validator(mode="after")
    def unique_order(self):
        if len({scene.order for scene in self.scenes}) != len(self.scenes):
            raise ValueError("A ordem de cada cena deve ser única.")
        return self


class ImportInput(Input):
    instance_id: Identifier
    manifest: Manifest


class MarkdownInput(Input):
    instance_id: Identifier
    markdown: str = Field(min_length=1, max_length=2_000_000)


class OrderInput(Input):
    scene_ids: list[Identifier] = Field(max_length=999)


class Review(Input):
    approve: bool


class Reconciliation(Input):
    acknowledge: bool = False


class ErrorView(BaseModel):
    code: str
    message: str


class MediaView(BaseModel):
    video: str | None = None
    frame: str | None = None
    frame_source: str | None = None


class FrameDependency(BaseModel):
    scene_id: str
    attempt_id: str


class AttemptView(BaseModel):
    id: str
    scene_id: str
    instance_id: str
    created_at: str
    updated_at: str
    state: str
    remote_id: str | None
    evidence: str | None
    files: MediaView
    dependencies: list[FrameDependency]
    error: ErrorView | None


class SceneView(SceneInput):
    id: str
    project_id: str
    state: str
    remote_id: str | None
    files: MediaView
    dependencies: list[FrameDependency]
    selected_attempt: str | None
    stale: bool
    error: ErrorView | None


class SceneDetail(SceneView):
    attempts: list[AttemptView]


class ProjectView(ProjectInput):
    id: str
    slug: str
    status: str
    created_at: str
    updated_at: str
    remote_id: str | None
    error: ErrorView | None
    total: int
    completed: int
    folder: str
    instance_name: str


class ProjectDetail(ProjectView):
    scenes: list[SceneDetail]
    references_available: list[str]


class InstanceView(InstanceInput):
    id: str
    auth: str
    availability: str
    credits: int | None
    credit_source: str | None
    checked_at: str | None
    error: str | None


class LogView(BaseModel):
    id: int
    at: str
    project_id: str | None
    scene_id: str | None
    attempt_id: str | None
    instance_id: str | None
    event: str
    detail: str | None
