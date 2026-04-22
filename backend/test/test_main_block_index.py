import importlib.util
import asyncio
import os
import sys
import types
from pathlib import Path
from unittest import mock


BACKEND_DIR = Path(__file__).resolve().parents[1]
MAIN_PATH = BACKEND_DIR / "main.py"


def _load_module_from_path(module_name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, str(module_path))
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_main_module(fake_document_audit_service_cls):
    config_module = types.ModuleType("config")
    config_module.API_PREFIX = "/api/v1"
    config_module.BASE_DIR = Path("/tmp/docagent-backend")
    config_module.DATA_DIR = Path("/tmp/docagent-backend/data")
    config_module.DOC_DIR = Path("/tmp/docagent-backend/doc")
    config_module.FILE_TYPE_DIRS = ["pdf"]
    config_module.DOUBAO_API_KEY = ""
    config_module.DOUBAO_DEFAULT_LLM_MODEL = "doubao-mini"

    fastapi_module = types.ModuleType("fastapi")
    fastapi_module.FastAPI = _FakeFastAPIApp
    fastapi_module.Request = object
    fastapi_module.Response = _FakeResponse
    fastapi_module.HTTPException = _FakeHTTPException

    cors_module = types.ModuleType("fastapi.middleware.cors")
    cors_module.CORSMiddleware = object
    exceptions_module = types.ModuleType("fastapi.exceptions")
    exceptions_module.RequestValidationError = Exception
    responses_module = types.ModuleType("fastapi.responses")
    responses_module.FileResponse = object
    responses_module.RedirectResponse = object
    responses_module.Response = _FakeResponse
    staticfiles_module = types.ModuleType("fastapi.staticfiles")
    staticfiles_module.StaticFiles = object

    api_module = types.ModuleType("api")
    api_module.router = object()
    api_module.BusinessException = Exception
    api_module.business_exception_handler = lambda *args, **kwargs: None
    api_module.validation_exception_handler = lambda *args, **kwargs: None
    api_module.generic_exception_handler = lambda *args, **kwargs: None

    app_module = types.ModuleType("app")
    app_core_module = types.ModuleType("app.core")
    app_services_module = types.ModuleType("app.services")
    document_audit_service_module = types.ModuleType("app.services.document_audit_service")
    document_audit_service_module.DocumentAuditService = fake_document_audit_service_cls
    document_service_module = types.ModuleType("app.services.document_service")
    document_service_module.DocumentService = _FakeDocumentService
    classification_service_module = types.ModuleType("app.services.classification_service")
    classification_service_module.ClassificationService = _FakeClassificationService
    lightrag_runtime_module = types.ModuleType("app.services.lightrag_runtime")
    lightrag_runtime_module.LightRAGRuntime = _FakeRuntime
    local_embedding_runtime_module = types.ModuleType("app.services.local_embedding_runtime")
    local_embedding_runtime_module.LocalEmbeddingRuntime = _FakeRuntime

    core_logger_module = types.ModuleType("app.core.logger")
    core_logger_module.logger = mock.Mock()
    core_logger_module.setup_logging = lambda *args, **kwargs: None
    core_logger_module.RequestContextMiddleware = type("RequestContextMiddleware", (), {})

    with mock.patch.dict(
        sys.modules,
        {
            "config": config_module,
            "fastapi": fastapi_module,
            "fastapi.middleware.cors": cors_module,
            "fastapi.exceptions": exceptions_module,
            "fastapi.responses": responses_module,
            "fastapi.staticfiles": staticfiles_module,
            "api": api_module,
            "app": app_module,
            "app.core": app_core_module,
            "app.services": app_services_module,
            "app.core.logger": core_logger_module,
            "app.services.classification_service": classification_service_module,
            "app.services.document_audit_service": document_audit_service_module,
            "app.services.document_service": document_service_module,
            "app.services.lightrag_runtime": lightrag_runtime_module,
            "app.services.local_embedding_runtime": local_embedding_runtime_module,
        },
        clear=False,
    ):
        return _load_module_from_path("main_under_test_block_index", MAIN_PATH)


class _FakeResponse:
    def __init__(self, *args, status_code: int = 200, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.status_code = status_code


class _FakeHTTPException(Exception):
    def __init__(self, status_code: int, detail: str = "Not Found"):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class _FakeRuntime:
    async def ensure_ready(self):
        return {"status": "healthy"}


class _FakeDocumentService:
    pass


class _FakeClassificationService:
    pass


class _FakeFastAPIApp:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.middlewares = []
        self.state = types.SimpleNamespace()

    def add_exception_handler(self, *args, **kwargs):
        return None

    def add_middleware(self, *args, **kwargs):
        self.middlewares.append((args, kwargs))
        return None

    def include_router(self, *args, **kwargs):
        return None

    def api_route(self, *args, **kwargs):
        def decorator(fn):
            return fn

        return decorator

    def get(self, *args, **kwargs):
        def decorator(fn):
            return fn

        return decorator

    def head(self, *args, **kwargs):
        def decorator(fn):
            return fn

        return decorator

    def mount(self, *args, **kwargs):
        return None


def test_refresh_document_audit_state_registers_local_only_before_audit():
    class FakeDocumentAuditService:
        def register_local_only_documents(self):
            return 2

        async def audit(self):
            return {
                "sqlite_documents": 12,
                "local_files": 31,
                "lightrag": {"status": "healthy"},
                "local_embedding": {"status": "healthy"},
            }

    module = _load_main_module(FakeDocumentAuditService)

    payload = asyncio.run(module.refresh_document_audit_state(register_local_only=True))

    assert payload["registered_local_only_documents"] == 2
    assert payload["sqlite_documents"] == 12
    assert payload["lightrag"]["status"] == "healthy"


def test_health_check_uses_runtime_audit_statuses():
    class FakeDocumentAuditService:
        def register_local_only_documents(self):
            return 0

        async def audit(self):
            return {
                "sqlite_documents": 5,
                "local_files": 7,
                "lightrag": {"status": "healthy"},
                "local_embedding": {"status": "healthy"},
            }

    module = _load_main_module(FakeDocumentAuditService)
    module.app.state.startup_reconciliation = {"status": "completed"}

    payload = asyncio.run(module.health_check())

    assert payload["status"] == "healthy"
    assert payload["checks"] == {"lightrag": "healthy", "local_embedding": "healthy"}
    assert payload["document_audit"]["local_files"] == 7
    assert payload["startup_reconciliation"] == {"status": "completed"}


def test_health_check_is_unhealthy_when_local_embedding_is_unhealthy():
    class FakeDocumentAuditService:
        def register_local_only_documents(self):
            return 0

        async def audit(self):
            return {
                "sqlite_documents": 5,
                "local_files": 7,
                "lightrag": {"status": "healthy"},
                "local_embedding": {"status": "unhealthy", "detail": "8011 connection refused"},
            }

    module = _load_main_module(FakeDocumentAuditService)

    payload = asyncio.run(module.health_check())

    assert payload["status"] == "unhealthy"
    assert payload["checks"] == {"lightrag": "healthy", "local_embedding": "unhealthy"}


def test_default_wildcard_cors_disables_credentials(monkeypatch):
    class FakeIndexingService:
        def audit_block_index(self):
            return {"documents": [], "rebuild_candidates": [], "orphan_block_ids": []}

        def index_document(self, document_id: str, force: bool = False):
            return {"document_id": document_id, "block_index_status": "ready"}

    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    module = _load_main_module(FakeIndexingService)

    cors_kwargs = module.app.middlewares[0][1]

    assert cors_kwargs["allow_origins"] == ["*"]
    assert cors_kwargs["allow_credentials"] is False


def test_explicit_cors_origins_keep_credentials_enabled(monkeypatch):
    class FakeIndexingService:
        def audit_block_index(self):
            return {"documents": [], "rebuild_candidates": [], "orphan_block_ids": []}

        def index_document(self, document_id: str, force: bool = False):
            return {"document_id": document_id, "block_index_status": "ready"}

    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:3000,https://docagent.example.com")
    module = _load_main_module(FakeIndexingService)

    cors_kwargs = module.app.middlewares[0][1]

    assert cors_kwargs["allow_origins"] == ["http://localhost:3000", "https://docagent.example.com"]
    assert cors_kwargs["allow_credentials"] is True


def test_default_uvicorn_options_use_single_worker_for_runtime_orchestration(monkeypatch):
    class FakeDocumentAuditService:
        def register_local_only_documents(self):
            return 0

        async def audit(self):
            return {
                "lightrag": {"status": "healthy"},
                "local_embedding": {"status": "healthy"},
            }

    monkeypatch.delenv("DEV_MODE", raising=False)
    monkeypatch.delenv("UVICORN_WORKERS", raising=False)
    module = _load_main_module(FakeDocumentAuditService)

    options = module._build_uvicorn_options()

    assert options["host"] == "0.0.0.0"
    assert options["port"] == 6008
    assert options["reload"] is False
    assert options["workers"] == 1


def test_uvicorn_worker_count_can_be_overridden_for_stateless_deployments(monkeypatch):
    class FakeDocumentAuditService:
        def register_local_only_documents(self):
            return 0

        async def audit(self):
            return {
                "lightrag": {"status": "healthy"},
                "local_embedding": {"status": "healthy"},
            }

    monkeypatch.setenv("UVICORN_WORKERS", "3")
    module = _load_main_module(FakeDocumentAuditService)

    options = module._build_uvicorn_options()

    assert options["workers"] == 3


def test_root_supports_head_for_single_port_health_probes():
    class FakeDocumentAuditService:
        def register_local_only_documents(self):
            return 0

        async def audit(self):
            return {
                "lightrag": {"status": "healthy"},
                "local_embedding": {"status": "healthy"},
            }

    module = _load_main_module(FakeDocumentAuditService)

    payload = asyncio.run(module.root_head())

    assert payload.status_code == 200


def test_frontend_dist_serving_is_disabled_by_default(monkeypatch):
    class FakeDocumentAuditService:
        def register_local_only_documents(self):
            return 0

        async def audit(self):
            return {
                "lightrag": {"status": "healthy"},
                "local_embedding": {"status": "healthy"},
            }

    monkeypatch.delenv("DOCAGENT_SERVE_FRONTEND_DIST", raising=False)
    module = _load_main_module(FakeDocumentAuditService)

    assert module._serve_frontend_dist() is False


def test_frontend_dist_serving_can_be_enabled(monkeypatch):
    class FakeDocumentAuditService:
        def register_local_only_documents(self):
            return 0

        async def audit(self):
            return {
                "lightrag": {"status": "healthy"},
                "local_embedding": {"status": "healthy"},
            }

    monkeypatch.setenv("DOCAGENT_SERVE_FRONTEND_DIST", "true")
    module = _load_main_module(FakeDocumentAuditService)

    assert module._serve_frontend_dist() is True


def test_root_returns_backend_payload_when_frontend_dist_is_disabled(monkeypatch):
    class FakeDocumentAuditService:
        def register_local_only_documents(self):
            return 0

        async def audit(self):
            return {
                "lightrag": {"status": "healthy"},
                "local_embedding": {"status": "healthy"},
            }

    monkeypatch.delenv("DOCAGENT_SERVE_FRONTEND_DIST", raising=False)
    module = _load_main_module(FakeDocumentAuditService)

    payload = asyncio.run(module.root())

    assert payload["message"] == "办公文档智能分类与检索系统后端API"
    assert payload["api_prefix"] == "/api/v1"


def test_spa_fallback_returns_404_when_frontend_dist_is_disabled(monkeypatch):
    class FakeDocumentAuditService:
        def register_local_only_documents(self):
            return 0

        async def audit(self):
            return {
                "lightrag": {"status": "healthy"},
                "local_embedding": {"status": "healthy"},
            }

    monkeypatch.delenv("DOCAGENT_SERVE_FRONTEND_DIST", raising=False)
    module = _load_main_module(FakeDocumentAuditService)

    try:
        asyncio.run(module.spa_fallback("documents"))
    except _FakeHTTPException as exc:
        assert exc.status_code == 404
        assert exc.detail == "Not Found"
    else:
        raise AssertionError("spa_fallback should return 404 when frontend dist serving is disabled")


def test_startup_reconciliation_runs_local_index_lightrag_and_classification(monkeypatch):
    class FakeDocumentAuditService:
        def register_local_only_documents(self):
            return 0

        async def audit(self):
            return {
                "lightrag": {"status": "healthy"},
                "local_embedding": {"status": "healthy"},
            }

    module = _load_main_module(FakeDocumentAuditService)
    monkeypatch.setenv("DOCAGENT_STARTUP_SYNC_ENABLED", "true")
    monkeypatch.setenv("DOCAGENT_STARTUP_LOCAL_INDEX_LIMIT", "7")
    monkeypatch.setenv("DOCAGENT_STARTUP_LIGHTRAG_LIMIT", "5")
    monkeypatch.setenv("DOCAGENT_STARTUP_CLASSIFICATION_LIMIT", "3")

    calls = []

    class FakeDocumentService:
        def backfill_local_index(self, **kwargs):
            calls.append(("backfill_local_index", kwargs))
            return {"total": 2, "success_count": 2}

        def recover_stale_lightrag_queue(self):
            calls.append(("recover_stale_lightrag_queue", {}))
            return {"status": "triggered", "triggered": True, "pending_documents": 2}

        def start_local_only_batch_import(self, **kwargs):
            calls.append(("start_local_only_batch_import", kwargs))
            return {"job_id": "job-1", "state": "running"}

        async def wait_for_batch_import(self):
            calls.append(("wait_for_batch_import", {}))

        def get_batch_import_status(self):
            calls.append(("get_batch_import_status", {}))
            return {"job_id": "job-1", "state": "completed", "succeeded": 1}

    class FakeClassificationService:
        def batch_classify_ready_documents(self, **kwargs):
            calls.append(("batch_classify_ready_documents", kwargs))
            return {"total": 1, "classified": 1, "needs_review": 0}

    payload = asyncio.run(
        module.run_startup_reconciliation(
            document_service_factory=FakeDocumentService,
            classification_service_factory=FakeClassificationService,
        )
    )

    assert payload["status"] == "completed"
    assert payload["local_index"]["success_count"] == 2
    assert payload["lightrag_recovery"]["triggered"] is True
    assert payload["lightrag_ingest"]["state"] == "completed"
    assert payload["classification"]["classified"] == 1
    assert calls == [
        (
            "backfill_local_index",
            {"limit": 7, "include_failed": False, "build_block_index": False},
        ),
        ("recover_stale_lightrag_queue", {}),
        (
            "start_local_only_batch_import",
            {"limit": 5, "concurrency": 1, "interval_seconds": 0.5, "include_failed": False},
        ),
        ("wait_for_batch_import", {}),
        ("get_batch_import_status", {}),
        (
            "batch_classify_ready_documents",
            {"limit": 3, "include_needs_review": True, "force": False},
        ),
    ]


def test_startup_reconciliation_can_be_disabled(monkeypatch):
    class FakeDocumentAuditService:
        def register_local_only_documents(self):
            return 0

        async def audit(self):
            return {
                "lightrag": {"status": "healthy"},
                "local_embedding": {"status": "healthy"},
            }

    module = _load_main_module(FakeDocumentAuditService)
    monkeypatch.setenv("DOCAGENT_STARTUP_SYNC_ENABLED", "false")

    def forbidden_factory():
        raise AssertionError("startup reconciliation should be disabled")

    payload = asyncio.run(
        module.run_startup_reconciliation(
            document_service_factory=forbidden_factory,
            classification_service_factory=forbidden_factory,
        )
    )

    assert payload == {"status": "disabled"}


def test_startup_sync_is_enabled_by_default(monkeypatch):
    class FakeDocumentAuditService:
        def register_local_only_documents(self):
            return 0

        async def audit(self):
            return {
                "lightrag": {"status": "healthy"},
                "local_embedding": {"status": "healthy"},
            }

    monkeypatch.delenv("DOCAGENT_STARTUP_SYNC_ENABLED", raising=False)
    module = _load_main_module(FakeDocumentAuditService)

    assert module._startup_sync_enabled() is True
