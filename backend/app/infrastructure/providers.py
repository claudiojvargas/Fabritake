import os
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

from filelock import FileLock, Timeout
from playwright.sync_api import Error as PlaywrightError, sync_playwright

from app.domain.workflow import ProviderStatus, Submission, WorkflowError

FIXTURES = Path(__file__).with_name("fixtures")
FLOW_URL = "https://labs.google/fx/tools/flow"


class BrowserInstanceManager:
    def __init__(self, root: Path):
        self.root = root
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="browser")
        self.sessions = {}
        self.playwright = None

    @staticmethod
    def profile(root: Path, instance_id: str):
        if not re.fullmatch(r"[0-9a-f]{32}", instance_id):
            raise WorkflowError("invalid_instance", "Identificador de instância inválido.", 400)
        path = root / instance_id
        if path.is_symlink() or path.resolve().parent != root.resolve():
            raise WorkflowError("invalid_profile", "Diretório de perfil inválido.")
        return path

    def call(self, action, instance_id):
        return self.executor.submit(getattr(self, "_" + action), instance_id).result()

    def _open(self, instance_id):
        if instance_id in self.sessions:
            return self._status(instance_id)
        profile = self.profile(self.root, instance_id)
        profile.mkdir(exist_ok=True, mode=0o700)
        lock = FileLock(profile / ".fabritake.lock", timeout=0)
        try:
            lock.acquire()
        except Timeout:
            return ProviderStatus("unknown", "blocked", message="O perfil está em uso por outro processo.")
        try:
            if self.playwright is None:
                self.playwright = sync_playwright().start()
            context = self.playwright.chromium.launch_persistent_context(
                str(profile), headless=False, executable_path=os.getenv("FABRITAKE_CHROMIUM_PATH") or None,
            )
        except (PlaywrightError, OSError):
            lock.release()
            return ProviderStatus("unknown", "blocked", message="Não foi possível abrir o Chromium. Verifique a instalação e a sessão gráfica.")
        self.sessions[instance_id] = (context, lock)
        context.on("close", lambda _: self._release(instance_id))
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(FLOW_URL, wait_until="domcontentloaded", timeout=20_000)
        except PlaywrightError:
            return ProviderStatus("unknown", "blocked", message="Navegador aberto. A navegação ao Flow falhou; verifique a página e a conexão.")
        return self._status(instance_id)

    def _release(self, instance_id):
        session = self.sessions.pop(instance_id, None)
        if session:
            session[1].release()

    def _status(self, instance_id):
        if instance_id not in self.sessions:
            return ProviderStatus("unknown", "closed", message="Abra o navegador para verificar a sessão manualmente.")
        context, _ = self.sessions[instance_id]
        try:
            pages = [urlsplit(page.url) for page in context.pages]
        except PlaywrightError:
            self._close(instance_id)
            return ProviderStatus("unknown", "closed")
        if any(page.hostname == "accounts.google.com" for page in pages):
            return ProviderStatus("manual_login", "manual", message="Verifique a página da conta Google no navegador.")
        if any(page.hostname == "labs.google" and "/tools/flow" in page.path for page in pages):
            return ProviderStatus("unknown", "diagnostic", message="Página do Flow localizada. Confirme login e disponibilidade na janela.")
        return ProviderStatus("unknown", "manual", message="Verifique a página aberta, permissões e eventuais desafios na janela.")

    def _close(self, instance_id):
        session = self.sessions.get(instance_id)
        if session:
            try:
                session[0].close()
            finally:
                self._release(instance_id)
        return ProviderStatus("unknown", "closed")

    def shutdown(self):
        def close_all():
            for instance_id in list(self.sessions):
                try:
                    self._close(instance_id)
                except PlaywrightError:
                    continue
            if self.playwright:
                self.playwright.stop()
                self.playwright = None

        try:
            self.executor.submit(close_all).result()
        finally:
            self.executor.shutdown()


class FakeVideoProvider:
    def status(self, instance_id):
        return ProviderStatus("simulated", "available")

    def prepare(self, request):
        if not all(path.is_file() for path in request.references):
            raise WorkflowError("missing_reference", "Uma referência configurada está ausente.")

    def submit(self, request):
        return Submission(f"sim-{request.attempt_id}", "fixture")

    def reconcile(self, instance_id, submission):
        return submission.evidence == "fixture"

    def wait(self, request, submission, stopping):
        if stopping():
            raise WorkflowError("interrupted", "Execução interrompida após registro da submissão.")

    def save_frame(self, request, submission, path):
        shutil.copyfile(self.fixture(request.order, "png"), path)
        return "fixture"

    def download(self, request, submission, path):
        shutil.copyfile(self.fixture(request.order, "mp4"), path)

    @staticmethod
    def fixture(order, extension):
        return FIXTURES / f"{(order - 1) % 3 + 1}.{extension}"


class GoogleFlowProvider:
    def __init__(self, browser: BrowserInstanceManager):
        self.browser = browser

    def status(self, instance_id):
        return self.browser.call("status", instance_id)

    def prepare(self, request):
        raise WorkflowError("provider_unverified", "A geração do Flow aguarda validação manual da interface e das permissões.")

    def submit(self, request):
        self.prepare(request)

    def reconcile(self, instance_id, submission):
        return False

    def wait(self, request, submission, stopping):
        self.prepare(request)

    def save_frame(self, request, submission, path):
        self.prepare(request)

    def download(self, request, submission, path):
        self.prepare(request)
