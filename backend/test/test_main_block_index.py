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
    config_module.DATA_DIR = Path("/tmp/docagent-backend/data")
    config_module.DOC_DIR = Path("/tmp/docagent-backend/doc")
    config_module.FILE_TYPE_DIRS = ["pdf"]
    config_module.DOUBAO_API_KEY = ""
    config_module.DOUBAO_DEFAULT_LLM_MODEL = "doubao-mini"

    fastapi_module = types.ModuleType("fastapi")
    fastapi_module.FastAPI = _FakeFastAPIApp
    fastapi_module.Request = object

    cors_module = types.ModuleType("fastapi.middleware.cors")
    cors_module.CORSMiddleware = object
    exceptions_module = types.ModuleType("fastapi.exceptions")
    exceptions_module.RequestValidationError = Exception
    responses_module = types.ModuleType("fastapi.responses")
    responses_module.RedirectResponse = object

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
            "api": api_module,
            "app": app_module,
            "app.core": app_core_module,
            "app.services": app_services_module,
            "app.core.logger": core_logger_module,
            "app.services.document_audit_service": document_audit_service_module,
        },
        clear=False,
    ):
        return _load_module_from_path("main_under_test_block_index", MAIN_PATH)


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

    payload = asyncio.run(module.health_check())

    assert payload["status"] == "healthy"
    assert payload["checks"] == {"lightrag": "healthy", "local_embedding": "healthy"}
    assert payload["document_audit"]["local_files"] == 7


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
