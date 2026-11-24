from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint, create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def uid():
    return uuid4().hex


def now():
    return datetime.now(timezone.utc).isoformat()


class Base(DeclarativeBase):
    pass


class Instance(Base):
    __tablename__ = "instances"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    name: Mapped[str]
    provider: Mapped[str]
    profile: Mapped[str] = mapped_column(unique=True)
    auth: Mapped[str] = mapped_column(default="unknown")
    availability: Mapped[str] = mapped_column(default="closed")
    credits: Mapped[int | None]
    credit_source: Mapped[str | None]
    checked_at: Mapped[str | None]
    error: Mapped[str | None]


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    title: Mapped[str]
    slug: Mapped[str] = mapped_column(unique=True)
    description: Mapped[str]
    language: Mapped[str]
    duration: Mapped[int | None]
    ratio: Mapped[str]
    provider: Mapped[str]
    instance_id: Mapped[str] = mapped_column(ForeignKey("instances.id"))
    status: Mapped[str] = mapped_column(default="draft", index=True)
    created_at: Mapped[str] = mapped_column(default=now)
    updated_at: Mapped[str] = mapped_column(default=now, onupdate=now)
    settings: Mapped[dict] = mapped_column(JSON)
    references: Mapped[list] = mapped_column(JSON)
    remote_id: Mapped[str | None]
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Scene(Base):
    __tablename__ = "scenes"
    __table_args__ = (UniqueConstraint("project_id", "order"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    order: Mapped[int]
    title: Mapped[str]
    prompt: Mapped[str]
    duration: Mapped[int | None]
    references: Mapped[list] = mapped_column(JSON)
    continuity: Mapped[str]
    state: Mapped[str] = mapped_column(default="pending")
    remote_id: Mapped[str | None]
    files: Mapped[dict] = mapped_column(JSON, default=dict)
    dependencies: Mapped[list] = mapped_column(JSON, default=list)
    selected_attempt: Mapped[str | None]
    stale: Mapped[bool] = mapped_column(default=False)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"), index=True)
    instance_id: Mapped[str] = mapped_column(ForeignKey("instances.id"))
    created_at: Mapped[str] = mapped_column(default=now)
    updated_at: Mapped[str] = mapped_column(default=now, onupdate=now)
    state: Mapped[str]
    remote_id: Mapped[str | None]
    evidence: Mapped[str | None]
    files: Mapped[dict] = mapped_column(JSON, default=dict)
    dependencies: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Log(Base):
    __tablename__ = "logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[str] = mapped_column(default=now)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    scene_id: Mapped[str | None]
    attempt_id: Mapped[str | None]
    instance_id: Mapped[str | None]
    event: Mapped[str]
    detail: Mapped[str | None]


def open_database(path: Path):
    engine = create_engine(URL.create("sqlite", database=str(path)), connect_args={"timeout": 10})

    @event.listens_for(engine, "connect")
    def configure(connection, _):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=FULL")
        cursor.close()

    return engine, sessionmaker(engine, expire_on_commit=False)
