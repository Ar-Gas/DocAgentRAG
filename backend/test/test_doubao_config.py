import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


BACKEND_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = BACKEND_DIR / "config.py"
MAIN_PATH = BACKEND_DIR / "main.py"
RETRIEVAL_SERVICE_PATH = BACKEND_DIR / "app" / "services" / "retrieval_service.py"
SMART_RETRIEVAL_PATH = BACKEND_DIR / "utils" / "smart_retrieval.py"


def _load_module_from_path(module_name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, str(module_path))
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _make_fake_retrieval_dependencies(llm_available: bool):
    app_module = types.ModuleType("app")
    app_services_module = types.ModuleType("app.services")
    app_errors_module = types.ModuleType("app.services.errors")
    app_errors_module.AppServiceError = type("AppServiceError", (Exception,), {})

    logger_module = types.ModuleType("utils.logger")
    logger_module.get_logger = lambda *args, **kwargs: mock.Mock()
    logger_module.log_retrieval = lambda fn: fn

    cache_module = types.ModuleType("utils.search_cache")
    cache_module.get_search_cache = lambda: mock.Mock(get=lambda *args, **kwargs: None)

    retriever_module = types.ModuleType("utils.retriever")
    retriever_module.batch_search_documents = lambda *args, **kwargs: []
    retriever_module.get_document_by_id = lambda *args, **kwargs: {}
    retriever_module.get_document_stats = lambda *args, **kwargs: {}
    retriever_module.get_ready_block_document_ids = lambda *args, **kwargs: set()
    retriever_module.get_query_parser = lambda *args, **kwargs: None
    retriever_module.hybrid_search = lambda *args, **kwargs: []
    retriever_module.keyword_search = lambda *args, **kwargs: []
    retriever_module.multimodal_search = lambda *args, **kwargs: []
    retriever_module.search_block_documents = lambda *args, **kwargs: {"documents": [], "results": [], "meta": {}}
    retriever_module.search_documents = lambda *args, **kwargs: []
    retriever_module.search_with_highlight = lambda *args, **kwargs: ([], {})

    smart_module = types.ModuleType("utils.smart_retrieval")
    smart_module.expand_query_keywords = lambda query: [query]
    smart_module.expand_query_with_llm = lambda query: [query]
    smart_module.is_llm_available = lambda: llm_available
    smart_module.smart_retrieval = lambda **kwargs: ([], {"expanded_queries": [], "expansion_method": None, "rerank_method": None, "total_candidates": 0})
    smart_module.summarize_retrieval_results = lambda *args, **kwargs: {}

    storage_module = types.ModuleType("utils.storage")
    storage_module.enrich_document_file_state = lambda doc: doc
    storage_module.get_all_documents = lambda: []
    storage_module.get_document_content_record = lambda document_id: {}
    storage_module.get_document_info = lambda document_id: {"id": document_id}
    storage_module.list_document_segments = lambda document_id: []

    return {
        "app": app_module,
        "app.services": app_services_module,
        "app.services.errors": app_errors_module,
        "utils.logger": logger_module,
        "utils.search_cache": cache_module,
        "utils.retriever": retriever_module,
        "utils.smart_retrieval": smart_module,
        "utils.storage": storage_module,
    }


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


class DoubaoConfigTests(unittest.TestCase):
    def setUp(self):
        self._original_env = os.environ.copy()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._original_env)
        for key in list(sys.modules.keys()):
            if key.startswith("config_under_test_") or key.startswith("main_under_test_"):
                sys.modules.pop(key, None)
            if key.startswith("retrieval_service_under_test_") or key.startswith("smart_retrieval_under_test_"):
                sys.modules.pop(key, None)
        sys.modules.pop("secrets_api", None)

    def _load_config(self, suffix: str, fake_secrets_module=None):
        module_name = f"config_under_test_{suffix}"
        sys.modules.pop(module_name, None)
        if fake_secrets_module is None:
            sys.modules.pop("secrets_api", None)
        else:
            sys.modules["secrets_api"] = fake_secrets_module
        return _load_module_from_path(module_name, CONFIG_PATH)

    def _load_retrieval_service(self, suffix: str, config_module, llm_available: bool, smart_module_override=None):
        fake_modules = _make_fake_retrieval_dependencies(llm_available=llm_available)
        if smart_module_override is not None:
            fake_modules["utils.smart_retrieval"] = smart_module_override
        module_name = f"retrieval_service_under_test_{suffix}"
        sys.modules.pop(module_name, None)
        with mock.patch.dict(sys.modules, {"config": config_module, **fake_modules}, clear=False):
            return _load_module_from_path(module_name, RETRIEVAL_SERVICE_PATH)

    def _load_smart_retrieval(self, suffix: str, config_module):
        module_name = f"smart_retrieval_under_test_{suffix}"
        sys.modules.pop(module_name, None)
        with mock.patch.dict(sys.modules, {"config": config_module}, clear=False):
            return _load_module_from_path(module_name, SMART_RETRIEVAL_PATH)

    def test_config_falls_back_to_env_when_secrets_api_module_missing(self):
        os.environ["DOUBAO_API_KEY"] = "env-doubao-key"
        os.environ["DOUBAO_EMBEDDING_API_URL"] = "https://env.example/embed"
        os.environ["DOUBAO_EMBEDDING_MODEL"] = "env-embedding-model"
        os.environ["DOUBAO_LLM_API_URL"] = "https://env.example/chat"
        os.environ["DOUBAO_MINI_LLM_MODEL"] = "env-mini-model"
        os.environ["DOUBAO_LLM_MODEL"] = "env-pro-model"

        module = self._load_config("no_secrets_module")

        self.assertEqual(module.DOUBAO_API_KEY, "env-doubao-key")
        self.assertEqual(module.DOUBAO_EMBEDDING_API_URL, "https://env.example/embed")
        self.assertEqual(module.DOUBAO_EMBEDDING_MODEL, "env-embedding-model")
        self.assertEqual(module.DOUBAO_LLM_API_URL, "https://env.example/chat")
        self.assertEqual(module.DOUBAO_MINI_LLM_MODEL, "env-mini-model")
        self.assertEqual(module.DOUBAO_LLM_MODEL, "env-pro-model")
        self.assertEqual(module.DOUBAO_DEFAULT_LLM_MODEL, "env-mini-model")
        self.assertTrue(module.LLM_AVAILABLE)

    def test_config_uses_partial_secrets_and_env_fallback_per_missing_symbol(self):
        os.environ["DOUBAO_EMBEDDING_MODEL"] = "env-fallback-embedding"
        os.environ["DOUBAO_MINI_LLM_MODEL"] = "env-fallback-mini"

        fake_secrets = types.ModuleType("secrets_api")
        fake_secrets.DOUBAO_API_KEY = "secrets-doubao-key"
        fake_secrets.DOUBAO_EMBEDDING_API_URL = "https://secrets.example/embed"
        fake_secrets.DOUBAO_LLM_API_URL = "https://secrets.example/chat"
        fake_secrets.DOUBAO_LLM_MODEL = "secrets-pro-model"

        module = self._load_config("partial_secrets", fake_secrets_module=fake_secrets)

        self.assertEqual(module.DOUBAO_API_KEY, "secrets-doubao-key")
        self.assertEqual(module.DOUBAO_EMBEDDING_API_URL, "https://secrets.example/embed")
        self.assertEqual(module.DOUBAO_LLM_API_URL, "https://secrets.example/chat")
        self.assertEqual(module.DOUBAO_LLM_MODEL, "secrets-pro-model")
        self.assertEqual(module.DOUBAO_EMBEDDING_MODEL, "env-fallback-embedding")
        self.assertEqual(module.DOUBAO_MINI_LLM_MODEL, "env-fallback-mini")
        self.assertEqual(module.DOUBAO_DEFAULT_LLM_MODEL, "env-fallback-mini")
        self.assertTrue(module.LLM_AVAILABLE)

    def test_config_llm_available_depends_only_on_doubao_api_key(self):
        fake_secrets = types.ModuleType("secrets_api")
        fake_secrets.DOUBAO_API_KEY = ""
        fake_secrets.DOUBAO_EMBEDDING_API_URL = "https://secrets.example/embed"
        fake_secrets.DOUBAO_EMBEDDING_MODEL = "secrets-embedding"
        fake_secrets.DOUBAO_LLM_API_URL = "https://secrets.example/chat"
        fake_secrets.DOUBAO_MINI_LLM_MODEL = "secrets-mini-model"
        fake_secrets.DOUBAO_LLM_MODEL = "secrets-pro-model"

        module = self._load_config("llm_false", fake_secrets_module=fake_secrets)
        self.assertFalse(module.LLM_AVAILABLE)

        fake_secrets.DOUBAO_API_KEY = "secrets-doubao-key"
        module = self._load_config("llm_true", fake_secrets_module=fake_secrets)
        self.assertTrue(module.LLM_AVAILABLE)

    def test_main_sync_helper_updates_llm_availability_and_logs(self):
        config_module = types.ModuleType("config")
        config_module.API_PREFIX = "/api/v1"
        config_module.DATA_DIR = Path("/tmp/docagent-data")
        config_module.DOC_DIR = Path("/tmp/docagent-doc")
        config_module.CHROMA_DB_PATH = Path("/tmp/docagent-chroma")
        config_module.FILE_TYPE_DIRS = []
        config_module.DOUBAO_API_KEY = ""
        config_module.DOUBAO_DEFAULT_LLM_MODEL = "mini-default"
        config_module.LLM_AVAILABLE = True

        fastapi_module = types.ModuleType("fastapi")
        fastapi_module.FastAPI = _FakeFastAPIApp
        fastapi_module.Request = object
        fastapi_module.HTTPException = Exception

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

        storage_module = types.ModuleType("utils.storage")
        storage_module.init_chroma_client = lambda: (None, None)
        storage_module.get_chroma_collection = lambda: None
        storage_module.get_all_documents = lambda: []
        storage_module.detect_and_lock_embedding_dim = lambda: None

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
                "utils.storage": storage_module,
                "utils.logger": logger_module,
            },
            clear=False,
        ):
            main_module = _load_module_from_path("main_under_test_helper", MAIN_PATH)

        fake_logger = mock.Mock()
        config_module.LLM_AVAILABLE = True
        available = main_module.sync_doubao_llm_availability(
            doubao_api_key="",
            doubao_default_llm_model="mini-default",
            config_module=config_module,
            logger_instance=fake_logger,
        )
        self.assertFalse(available)
        self.assertFalse(config_module.LLM_AVAILABLE)
        fake_logger.warning.assert_called_once()

        fake_logger = mock.Mock()
        config_module.LLM_AVAILABLE = False
        available = main_module.sync_doubao_llm_availability(
            doubao_api_key="doubao-key",
            doubao_default_llm_model="mini-default",
            config_module=config_module,
            logger_instance=fake_logger,
        )
        self.assertTrue(available)
        self.assertTrue(config_module.LLM_AVAILABLE)
        fake_logger.info.assert_called_once_with("LLM provider: Doubao, model: mini-default")

    def test_retrieval_service_llm_status_reports_doubao_only_payload(self):
        config_module = types.ModuleType("config")
        config_module.DOUBAO_API_KEY = "doubao-key"
        config_module.DOUBAO_DEFAULT_LLM_MODEL = "doubao-mini-for-test"

        module = self._load_retrieval_service(
            "llm_status_doubao_only",
            config_module=config_module,
            llm_available=True,
        )
        payload = module.RetrievalService().llm_status()

        self.assertEqual(
            payload,
            {
                "llm_available": True,
                "provider": "doubao",
                "doubao_configured": True,
                "default_model": "doubao-mini-for-test",
            },
        )

    def test_smart_retrieval_uses_default_model_for_doubao_call(self):
        config_module = types.ModuleType("config")
        config_module.DOUBAO_API_KEY = "doubao-key"
        config_module.DOUBAO_DEFAULT_LLM_MODEL = "doubao-mini-for-test"
        config_module.DOUBAO_LLM_API_URL = "https://doubao.test/chat"

        module = self._load_smart_retrieval("default_model", config_module=config_module)
        module._llm_client = None
        module._llm_provider = None

        fake_response = mock.Mock()
        fake_response.status_code = 200
        fake_response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}

        with mock.patch.dict(
            os.environ,
            {"DOUBAO_API_KEY": "doubao-key", "DOUBAO_LLM_MODEL": "doubao-pro-for-test"},
            clear=False,
        ):
            with mock.patch.object(module.requests, "post", return_value=fake_response) as post_mock:
                content = module._call_llm("hello", max_tokens=16, temperature=0.2)

        self.assertEqual(content, "ok")
        self.assertEqual(post_mock.call_args.kwargs["json"]["model"], "doubao-mini-for-test")

    def test_smart_retrieval_runtime_path_uses_default_model_when_env_pro_conflicts(self):
        config_module = types.ModuleType("config")
        config_module.DOUBAO_API_KEY = "doubao-key"
        config_module.DOUBAO_DEFAULT_LLM_MODEL = "doubao-mini-for-runtime"
        config_module.DOUBAO_LLM_API_URL = "https://doubao.test/chat"

        module = self._load_smart_retrieval("runtime_default_model", config_module=config_module)
        module._llm_client = None
        module._llm_provider = None

        fake_response = mock.Mock()
        fake_response.status_code = 200
        fake_response.json.return_value = {"choices": [{"message": {"content": "扩展词A\n扩展词B"}}]}

        captured_queries = []

        def fake_search(expanded_query, limit=10):
            captured_queries.append((expanded_query, limit))
            return [
                {
                    "document_id": f"doc-{expanded_query}",
                    "chunk_index": 0,
                    "similarity": 0.9,
                    "content_snippet": f"{expanded_query} content",
                    "filename": f"{expanded_query}.txt",
                }
            ]

        with mock.patch.dict(
            os.environ,
            {"DOUBAO_LLM_MODEL": "doubao-pro-env-conflict"},
            clear=False,
        ):
            with mock.patch.object(module.requests, "post", return_value=fake_response) as post_mock:
                results, meta = module.smart_retrieval(
                    query="原始查询",
                    search_func=fake_search,
                    limit=3,
                    use_query_expansion=True,
                    use_llm_rerank=False,
                    expansion_method="llm",
                )

        self.assertTrue(results)
        self.assertEqual(meta["expansion_method"], "llm")
        self.assertGreaterEqual(len(captured_queries), 1)
        self.assertEqual(post_mock.call_args.kwargs["json"]["model"], "doubao-mini-for-runtime")

    def test_retrieval_service_smart_llm_path_uses_default_model_when_env_pro_conflicts(self):
        config_module = types.ModuleType("config")
        config_module.DOUBAO_API_KEY = "doubao-key"
        config_module.DOUBAO_DEFAULT_LLM_MODEL = "doubao-mini-via-service"
        config_module.DOUBAO_LLM_API_URL = "https://doubao.test/chat"
        smart_module = self._load_smart_retrieval("runtime_via_service", config_module=config_module)
        smart_module._llm_client = None
        smart_module._llm_provider = None

        service_module = self._load_retrieval_service(
            "service_runtime_default_model",
            config_module=config_module,
            llm_available=True,
            smart_module_override=smart_module,
        )

        fake_response = mock.Mock()
        fake_response.status_code = 200
        fake_response.json.return_value = {"choices": [{"message": {"content": "扩展词A"}}]}

        def fake_hybrid_search(**kwargs):
            return [
                {
                    "document_id": "doc-1",
                    "chunk_index": 0,
                    "similarity": 0.88,
                    "content_snippet": "预算说明",
                    "filename": "budget.txt",
                }
            ]

        with mock.patch.dict(os.environ, {"DOUBAO_LLM_MODEL": "doubao-pro-env-conflict"}, clear=False):
            with mock.patch.object(service_module, "hybrid_search", side_effect=fake_hybrid_search):
                with mock.patch.object(smart_module.requests, "post", return_value=fake_response) as post_mock:
                    payload = service_module.RetrievalService().smart(
                        query="预算",
                        limit=2,
                        use_query_expansion=True,
                        use_llm_rerank=False,
                        expansion_method="llm",
                        file_types=None,
                    )

        self.assertGreaterEqual(payload["total"], 1)
        self.assertEqual(post_mock.call_args.kwargs["json"]["model"], "doubao-mini-via-service")


if __name__ == "__main__":
    unittest.main()
