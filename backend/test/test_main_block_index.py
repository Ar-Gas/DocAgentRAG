import importlib.util
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


def _load_main_module(fake_indexing_service_cls):
    config_module = types.ModuleType("config")
    config_module.API_PREFIX = "/api/v1"
    config_module.DATA_DIR = Path("/tmp/docagent-backend/data")
    config_module.DOC_DIR = Path("/tmp/docagent-backend/doc")
    config_module.CHROMA_DB_PATH = Path("/tmp/docagent-backend/chromadb")
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
    app_infra_module = types.ModuleType("app.infra")
    app_infra_repositories_module = types.ModuleType("app.infra.repositories")
    app_services_module = types.ModuleType("app.services")

    embedding_provider_module = types.ModuleType("app.infra.embedding_provider")
    embedding_provider_module.detect_and_lock_embedding_dim = lambda: None

    class _FakeDocumentRepository:
        def __init__(self, data_dir=None):
            self.data_dir = data_dir

        def list_all(self):
            return []

        def get(self, document_id):
            return {"id": document_id}

        def update(self, document_id, updated_info):
            return True

    document_repository_module = types.ModuleType("app.infra.repositories.document_repository")
    document_repository_module.DocumentRepository = _FakeDocumentRepository

    vector_store_module = types.ModuleType("app.infra.vector_store")
    vector_store_module.init_chroma_client = lambda: (object(), object())
    vector_store_module._chroma_client = object()
    vector_store_module._chroma_block_collection = object()

    indexing_service_module = types.ModuleType("app.services.indexing_service")
    indexing_service_module.IndexingService = fake_indexing_service_cls

    logger_module = types.ModuleType("utils.logger")
    logger_module.setup_logging = lambda: None

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
            "app.infra": app_infra_module,
            "app.infra.repositories": app_infra_repositories_module,
            "app.services": app_services_module,
            "app.infra.embedding_provider": embedding_provider_module,
            "app.infra.repositories.document_repository": document_repository_module,
            "app.infra.vector_store": vector_store_module,
            "app.services.indexing_service": indexing_service_module,
            "utils.logger": logger_module,
        },
        clear=False,
    ):
        return _load_module_from_path("main_under_test_block_index", MAIN_PATH)


class _FakeFastAPIApp:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def add_exception_handler(self, *args, **kwargs):
        return None

    def add_middleware(self, *args, **kwargs):
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


def test_startup_block_check_only_reports_candidates_by_default(monkeypatch):
    calls = []

    class FakeIndexingService:
        def audit_block_index(self):
            return {
                "documents": [
                    {"document_id": "doc-1", "filename": "budget.pdf", "rebuild_reasons": ["missing_blocks"]},
                ],
                "rebuild_candidates": ["doc-1"],
                "orphan_block_ids": [],
            }

        def index_document(self, document_id: str, force: bool = False):
            calls.append((document_id, force))
            return {"document_id": document_id, "block_index_status": "ready"}

    monkeypatch.delenv("AUTO_REBUILD_BLOCK_INDEX_ON_STARTUP", raising=False)
    module = _load_main_module(FakeIndexingService)

    payload = module.check_and_rebuild_block_indexes()

    assert payload["rebuild_candidates"] == ["doc-1"]
    assert calls == []


def test_startup_block_check_can_auto_rebuild_candidates(monkeypatch):
    calls = []

    class FakeIndexingService:
        def audit_block_index(self):
            return {
                "documents": [
                    {"document_id": "doc-1", "filename": "budget.pdf", "rebuild_reasons": ["missing_blocks"]},
                    {"document_id": "doc-2", "filename": "contract.docx", "rebuild_reasons": ["status_failed"]},
                ],
                "rebuild_candidates": ["doc-1", "doc-2"],
                "orphan_block_ids": [],
            }

        def index_document(self, document_id: str, force: bool = False):
            calls.append((document_id, force))
            return {"document_id": document_id, "block_index_status": "ready"}

    monkeypatch.setenv("AUTO_REBUILD_BLOCK_INDEX_ON_STARTUP", "true")
    module = _load_main_module(FakeIndexingService)

    payload = module.check_and_rebuild_block_indexes()

    assert payload["rebuild_candidates"] == ["doc-1", "doc-2"]
    assert calls == [("doc-1", True), ("doc-2", True)]
