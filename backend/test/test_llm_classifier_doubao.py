import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


BACKEND_DIR = Path(__file__).resolve().parents[1]
LLM_CLASSIFIER_PATH = BACKEND_DIR / "utils" / "llm_classifier.py"


def _load_llm_classifier_module(suffix: str, config_module: types.ModuleType):
    module_name = f"llm_classifier_under_test_{suffix}"
    spec = importlib.util.spec_from_file_location(module_name, str(LLM_CLASSIFIER_PATH))
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    with mock.patch.dict(sys.modules, {"config": config_module}, clear=False):
        spec.loader.exec_module(module)
    return module


def _load_llm_classifier_module_with_openai_guard(suffix: str, config_module: types.ModuleType):
    real_import = __import__

    def guarded_import(name, *args, **kwargs):
        if name == "openai":
            raise AssertionError("module import should not touch openai")
        return real_import(name, *args, **kwargs)

    with mock.patch("builtins.__import__", side_effect=guarded_import):
        return _load_llm_classifier_module(suffix, config_module)


def _load_llm_classifier_module_without_config(suffix: str):
    module_name = f"llm_classifier_under_test_{suffix}"
    spec = importlib.util.spec_from_file_location(module_name, str(LLM_CLASSIFIER_PATH))
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None

    real_import = __import__

    def guarded_import(name, *args, **kwargs):
        if name == "config":
            raise ModuleNotFoundError("No module named 'config'")
        return real_import(name, *args, **kwargs)

    with mock.patch("builtins.__import__", side_effect=guarded_import):
        spec.loader.exec_module(module)
    return module


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class LLMClassifierDoubaoTests(unittest.TestCase):
    def _fake_config(self):
        config = types.ModuleType("config")
        config.DOUBAO_API_KEY = "doubao-test-key"
        config.DOUBAO_LLM_API_URL = "https://doubao.test/chat/completions"
        config.DOUBAO_DEFAULT_LLM_MODEL = "doubao-mini-for-test"
        return config

    def test_get_llm_client_uses_doubao_config_without_openai_sdk(self):
        classifier = _load_llm_classifier_module_with_openai_guard("client_config", self._fake_config())
        classifier._llm_client = None

        client = classifier._get_llm_client()

        self.assertEqual(client["api_key"], "doubao-test-key")
        self.assertEqual(client["base_url"], "https://doubao.test/chat/completions")
        self.assertEqual(client["model"], "doubao-mini-for-test")

    def test_classify_with_llm_posts_using_default_model(self):
        classifier = _load_llm_classifier_module("classify_runtime", self._fake_config())
        classifier._llm_client = None

        fake_client = {
            "api_key": "doubao-test-key",
            "base_url": "https://doubao.test/chat/completions",
            "model": "doubao-mini-for-test",
        }
        fake_response = _FakeResponse(
            status_code=200,
            payload={"choices": [{"message": {"content": "技术文档-编程开发"}}]},
        )

        doc_info = {
            "id": "doc-1",
            "filename": "api.md",
            "preview_content": "这是一个后端接口文档。",
            "file_type": ".md",
            "created_at": 1700000000,
            "created_at_iso": "2023-11-14T22:13:20",
        }

        with mock.patch.object(classifier, "_get_llm_client", return_value=fake_client):
            with mock.patch.object(classifier.requests, "post", return_value=fake_response) as mock_post:
                result = classifier.classify_with_llm(doc_info)

        expected = {
            "document_id": "doc-1",
            "filename": "api.md",
            "content_keywords": [],
            "content_category": "技术文档-编程开发",
            "file_type": "md",
            "time_group": "2023年11月",
            "timestamp": 1700000000,
            "created_at_iso": "2023-11-14T22:13:20",
            "classification_path": "技术文档-编程开发/md/2023年11月",
            "classification_method": "llm",
        }
        self.assertEqual(result, expected)

        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer doubao-test-key")
        self.assertEqual(kwargs["json"]["model"], "doubao-mini-for-test")
        self.assertEqual(kwargs["json"]["max_tokens"], 50)
        self.assertEqual(kwargs["json"]["temperature"], 0.1)
        self.assertEqual(kwargs["timeout"], 30)

    def test_is_llm_available_delegates_to_get_llm_client(self):
        classifier = _load_llm_classifier_module("llm_available_delegate", self._fake_config())

        with mock.patch.object(classifier, "_get_llm_client", return_value={"api_key": "x"}) as mock_get:
            self.assertTrue(classifier.is_llm_available())
            mock_get.assert_called_once_with()

        with mock.patch.object(classifier, "_get_llm_client", return_value=None) as mock_get:
            self.assertFalse(classifier.is_llm_available())
            mock_get.assert_called_once_with()

    def test_fallback_without_config_uses_doubao_mini_model_as_default(self):
        with mock.patch.dict(
            "os.environ",
            {
                "DOUBAO_API_KEY": "fallback-key",
                "DOUBAO_LLM_API_URL": "https://fallback.example/chat",
                "DOUBAO_MINI_LLM_MODEL": "mini-from-env",
            },
            clear=True,
        ):
            classifier = _load_llm_classifier_module_without_config("fallback_without_config")
            classifier._llm_client = None

            client = classifier._get_llm_client()

        self.assertIsNotNone(client)
        self.assertEqual(client["api_key"], "fallback-key")
        self.assertEqual(client["base_url"], "https://fallback.example/chat")
        self.assertEqual(client["model"], "mini-from-env")


if __name__ == "__main__":
    unittest.main()
