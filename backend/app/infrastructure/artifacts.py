import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
from pathlib import Path, PureWindowsPath

from app.domain.workflow import WorkflowError
from app.infrastructure.providers import FIXTURES


def slug(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:70].rstrip("-") or "sem-titulo"


def safe(root: Path, relative: str):
    if not relative or "\\" in relative or ":" in relative or "\x00" in relative:
        raise WorkflowError("invalid_path", "Caminho inválido.", 400)
    parts = relative.split("/")
    if any(part in ("", ".", "..") or part.endswith((" ", ".")) or PureWindowsPath(part).is_reserved() for part in parts):
        raise WorkflowError("invalid_path", "Caminho inválido.", 400)
    path = root.joinpath(*parts)
    if not path.resolve().is_relative_to(root.resolve()) or any(
        root.joinpath(*parts[:index]).is_symlink() for index in range(1, len(parts) + 1)
    ):
        raise WorkflowError("invalid_path", "Caminho fora do armazenamento do projeto.", 400)
    return path


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".tmp-", delete=False) as temporary:
        temp = Path(temporary.name)
        try:
            temporary.write(data)
            temporary.flush()
            os.fsync(temporary.fileno())
        except BaseException:
            temporary.close()
            temp.unlink(missing_ok=True)
            raise
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


class ArtifactStore:
    def __init__(self, root):
        self.root = root

    def folder(self, project):
        return safe(self.root, project.slug)

    def initialize(self, project):
        root = self.folder(project)
        for name in ("referencias", "videos", "frames", "tentativas", "logs", "edicao"):
            safe(root, name).mkdir(parents=True, exist_ok=True)
        return root

    @staticmethod
    def validate_reference_name(relative):
        if not re.fullmatch(r"referencias/[a-zA-Z0-9][a-zA-Z0-9_.-]*\.(png|jpe?g|webp)", relative):
            raise WorkflowError("invalid_reference", "Use um arquivo PNG, JPEG ou WebP de referencias/.", 422)
    def reference(self, project, relative):
        self.validate_reference_name(relative)
        path = safe(self.folder(project), relative)
        if not path.is_file():
            raise WorkflowError("missing_reference", "Envie o arquivo de referência antes de usá-lo.", 422)
        return path

    def attempt_directory(self, project, scene, attempt):
        return safe(self.folder(project), f"tentativas/{scene.id}/{attempt.id}")

    def select(self, project, scene, attempt, old_files):
        root = self.folder(project)
        number = f"{scene.order:02d}"
        files = {
            "video": f"videos/{number}-{slug(scene.title)}.mp4",
            "frame": f"frames/{number}-frame-final.png",
            "frame_source": attempt.files["frame_source"],
        }
        copies = []
        for kind in ("video", "frame"):
            dest = safe(root, files[kind])
            source = safe(root, attempt.files[kind])
            if dest.exists():
                if self.same_content(dest, source):
                    continue  # A prior promotion may have stopped before the DB commit.
                old = old_files.get(kind)
                if not old or scene.files.get(kind) != files[kind] or not self.same_content(dest, safe(root, old)):
                    raise WorkflowError("artifact_conflict", "O destino contém mídia que não pertence à seleção da cena.")
            copies.append((source, dest))
        marker = safe(self.attempt_directory(project, scene, attempt), "selecao.json")
        atomic_write(marker, json.dumps(files).encode())
        for source, dest in copies:
            self.copy_atomic(source, dest)
        return files

    @staticmethod
    def same_content(first, second):
        if first.stat().st_size != second.stat().st_size:
            return False
        with first.open("rb") as a, second.open("rb") as b:
            return hashlib.file_digest(a, "sha256").digest() == hashlib.file_digest(b, "sha256").digest()

    @staticmethod
    def copy_atomic(source, dest):
        with tempfile.NamedTemporaryFile(dir=dest.parent, prefix=".tmp-", delete=False) as temporary:
            path = Path(temporary.name)
            try:
                with source.open("rb") as handle:
                    shutil.copyfileobj(handle, temporary)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary.close()
                os.replace(path, dest)
            finally:
                temporary.close()
                path.unlink(missing_ok=True)


class MediaValidator:
    def __init__(self):
        self.ffmpeg = shutil.which(os.getenv("FABRITAKE_FFMPEG", "ffmpeg"))
        self.ffprobe = shutil.which(os.getenv("FABRITAKE_FFPROBE", "ffprobe"))
        self.hashes = json.loads((FIXTURES / "hashes.json").read_text())

    @staticmethod
    def run(command, timeout=120):
        try:
            return subprocess.run(command, check=True, capture_output=True, timeout=timeout).stdout
        except (subprocess.SubprocessError, OSError):
            raise WorkflowError("invalid_media", "A mídia não pôde ser lida ou decodificada.") from None

    def validate(self, path, kind, fixture=None):
        if not path.is_file() or path.is_symlink() or path.stat().st_size == 0:
            raise WorkflowError("invalid_media", "Arquivo ausente ou vazio.")
        with path.open("rb") as handle:
            header = handle.read(12)
        expected = header[4:8] == b"ftyp" if kind == "video" else header.startswith(b"\x89PNG\r\n\x1a\n")
        if not expected:
            raise WorkflowError("invalid_media", "Formato de mídia incompatível com a extensão.")
        if fixture and self.hashes.get(fixture) != hashlib.sha256(path.read_bytes()).hexdigest():
            raise WorkflowError("invalid_media", "O conteúdo da fixture diverge do arquivo validado.")
        if not self.ffmpeg or not self.ffprobe:
            if fixture:
                return
            raise WorkflowError("media_tools_missing", "Instale FFmpeg e FFprobe para validar mídia externa.")
        probe = self.run([self.ffprobe, "-v", "error", "-select_streams", "v:0", "-show_streams", "-of", "json", str(path)])
        if not json.loads(probe).get("streams"):
            raise WorkflowError("invalid_media", "Nenhum fluxo de imagem encontrado.")
        self.run([self.ffmpeg, "-nostdin", "-v", "error", "-xerror", "-i", str(path), "-map", "0:v:0", "-f", "null", "-"])

    def extract(self, source, destination):
        if not self.ffmpeg:
            raise WorkflowError("media_tools_missing", "Instale FFmpeg para extrair o frame final.")
        # image2 update replaces the PNG for each decoded frame, leaving the last one.
        self.run([self.ffmpeg, "-nostdin", "-y", "-v", "error", "-i", str(source), "-map", "0:v:0",
                  "-fps_mode", "passthrough", "-update", "1", str(destination)])
        return "ffmpeg"
