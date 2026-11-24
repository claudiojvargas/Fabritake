import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.routes import router
from app.config import ROOT, origins, storage_path
from app.domain.workflow import WorkflowError
from app.runtime import Runtime


def create_app(root: Path | None = None, run_worker=True):
    @asynccontextmanager
    async def lifespan(application):
        runtime = Runtime(root or storage_path())
        application.state.runtime = runtime
        if run_worker:
            runtime.thread.start()
        try:
            yield
        finally:
            runtime.close()

    app = FastAPI(title="Fabritake", lifespan=lifespan)
    app.include_router(router)
    configured_origins = set(origins())
    hosts = ["localhost", "127.0.0.1", "[::1]"]
    hosts.extend(h.strip() for h in os.getenv("FABRITAKE_EXTRA_HOSTS", "").split(",") if h.strip() and "*" not in h)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)
    app.add_middleware(CORSMiddleware, allow_origins=list(configured_origins), allow_methods=["GET", "POST", "PUT", "DELETE"],
                       allow_headers=["Content-Type", "X-Fabritake"])

    @app.middleware("http")
    async def local_requests(request: Request, call_next):
        if request.url.path.startswith("/api/") and request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            same_origin = f"{request.url.scheme}://{request.url.netloc}"
            if (request.headers.get("x-fabritake") != "local" or
                    (origin is not None and origin not in configured_origins | {same_origin})):
                return JSONResponse({"error": {"code": "origin_denied", "message": "Requisição local não autorizada."}}, 403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        return response

    @app.exception_handler(WorkflowError)
    async def workflow_error(_request, error):
        return JSONResponse({"error": error.as_dict()}, status_code=error.status)

    @app.exception_handler(ValidationError)
    @app.exception_handler(RequestValidationError)
    async def validation_error(_request, error):
        details = [{"field": ".".join(map(str, item["loc"])), "message": item["msg"]} for item in error.errors()]
        return JSONResponse({"error": {"code": "invalid_input", "message": "Revise os dados informados.", "details": details}}, 422)

    @app.exception_handler(OSError)
    async def filesystem_error(_request, _error):
        return JSONResponse({"error": {"code": "local_io", "message": "Falha ao acessar o armazenamento local."}}, 500)

    frontend = ROOT / "frontend" / "dist"
    if (frontend / "index.html").is_file():
        app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

        @app.get("/", include_in_schema=False)
        def home():
            return FileResponse(frontend / "index.html")

    return app


app = create_app()
