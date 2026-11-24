import logging
from contextlib import contextmanager
from pathlib import Path
from threading import Event, RLock, Thread

from alembic import command
from alembic.config import Config
from filelock import FileLock
from sqlalchemy import update

from app.application.orchestration import RecoveryService, SceneOrchestrator
from app.application.projects import ProjectService
from app.infrastructure.artifacts import ArtifactStore, MediaValidator
from app.infrastructure.database import Instance, open_database
from app.infrastructure.providers import BrowserInstanceManager, FakeVideoProvider, GoogleFlowProvider

log = logging.getLogger(__name__)


def upgrade(engine):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


class Runtime:
    def __init__(self, root):
        self.root = root
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        database = root / "database"
        database.mkdir(exist_ok=True, mode=0o700)
        self.lease = FileLock(database / "runtime.lock", timeout=0)
        self.lease.acquire()
        try:
            for name in ("projects", "browser_profiles"):
                (root / name).mkdir(exist_ok=True, mode=0o700)
            self.engine, self.db = open_database(database / "fabritake.sqlite3")
            upgrade(self.engine)
            with self.db.begin() as db:
                db.execute(update(Instance).where(Instance.provider == "flow").values(auth="unknown", availability="closed"))
            self.lock = RLock()
            self.stopping = Event()
            self.wake = Event()
            self.browser = BrowserInstanceManager(root / "browser_profiles")
            self.projects = ProjectService(ArtifactStore(root / "projects"))
            self.worker = SceneOrchestrator(
                self.db, self.lock, self.projects, MediaValidator(),
                {"simulated": FakeVideoProvider(), "flow": GoogleFlowProvider(self.browser)}, self.stopping.is_set,
            )
            self.recovery = RecoveryService(self.worker)
            self.recovery.recover()
            self.thread = Thread(target=self.loop, name="generation-worker")
        except BaseException:
            self.lease.release()
            raise

    @contextmanager
    def write(self):
        with self.lock, self.db() as db:
            yield db
            db.commit()
        self.wake.set()

    def loop(self):
        while not self.stopping.is_set():
            self.wake.clear()
            try:
                if self.worker.step():
                    continue
            except Exception as error:
                log.error("worker_iteration_failed type=%s", type(error).__name__)
                try:
                    self.recovery.recover()
                except Exception as recovery_error:
                    log.error("worker_recovery_failed type=%s", type(recovery_error).__name__)
            self.wake.wait(1)

    def close(self):
        self.stopping.set()
        self.wake.set()
        if self.thread.is_alive():
            self.thread.join()
        try:
            self.browser.shutdown()
        finally:
            self.engine.dispose()
            self.lease.release()
