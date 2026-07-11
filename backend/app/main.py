from pathlib import Path
from contextlib import asynccontextmanager
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles

from app.api.assets import router as assets_router
from app.api.datasets import router as datasets_router
from app.api.training import router as training_router
from app.api.models import router as models_router
from app.api.system import router as system_router
from app.api.prelabels import router as prelabels_router
from app.core.database import Database
from app.core.paths import ProjectPaths
from app.core.spa import SpaStaticFiles
from app.services.training_worker import TrainingWorker


def create_app(root: Path | None = None, start_worker: bool = True) -> FastAPI:
    project_root = (root or Path(__file__).resolve().parents[2]).resolve()
    os.environ.setdefault("YOLO_CONFIG_DIR", str(project_root / "resources"))
    database = Database(project_root / "data" / "studio.db")
    import app.models  # noqa: F401
    database.create_all()
    (project_root / "uploads" / "assets").mkdir(parents=True, exist_ok=True)
    worker = TrainingWorker(project_root, database)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        worker.start()
        try:
            yield
        finally:
            worker.stop()

    app = FastAPI(title="YOLO26 Studio API", version="1.0.0", lifespan=lifespan if start_worker else None)
    app.state.root = project_root
    app.state.paths = ProjectPaths(project_root)
    app.state.database = database
    app.state.worker = worker
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(assets_router, prefix="/api/v1")
    app.include_router(datasets_router, prefix="/api/v1")
    app.include_router(training_router, prefix="/api/v1")
    app.include_router(models_router, prefix="/api/v1")
    app.include_router(system_router, prefix="/api/v1")
    app.include_router(prelabels_router, prefix="/api/v1")


    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, dict) else {"code": "HTTP_ERROR", "message": str(exc.detail)}
        return JSONResponse(status_code=exc.status_code, content={"error": detail})

    @app.exception_handler(ValueError)
    async def value_error(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"error": {"code": "VALIDATION_ERROR", "message": str(exc)}})

    @app.exception_handler(RequestValidationError)
    async def request_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"error": {"code": "VALIDATION_ERROR", "message": "请求参数无效", "details": exc.errors()}})

    @app.get("/api/v1/health")
    def health() -> dict:
        return {"status": "ok", "projectRoot": project_root.as_posix()}

    app.mount("/media", StaticFiles(directory=project_root / "uploads"), name="media")
    frontend_dist = project_root / "frontend" / "dist"
    if frontend_dist.is_dir():
        app.mount("/", SpaStaticFiles(directory=frontend_dist, html=True), name="frontend")
    return app


app = create_app()
