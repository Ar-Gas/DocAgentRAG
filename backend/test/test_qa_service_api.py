import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.qa as qa_api  # noqa: E402
from app.core.database import connect_sqlite  # noqa: E402
from app.domain.llm.gateway import LLMResponse  # noqa: E402
from app.infra.repositories.qa_session_repository import QASessionRepository  # noqa: E402
from app.services.qa_service import QAService  # noqa: E402


def _create_qa_repo(tmp_path: Path) -> QASessionRepository:
    db_path = tmp_path / "docagent.db"
    with connect_sqlite(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE qa_sessions (
                id TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                doc_ids TEXT NOT NULL,
                answer TEXT NOT NULL,
                citations TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
    return QASessionRepository(db_path=db_path, data_dir=tmp_path)


async def _read_streaming_response(response):
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)
    return "".join(chunks)


def test_reciprocal_rank_fusion_supports_document_id_hits():
    from app.domain.retrieval.fusion import reciprocal_rank_fusion

    fused = reciprocal_rank_fusion(
        [
            {"document_id": "doc-1", "filename": "budget-plan.pdf"},
            {"document_id": "doc-2", "filename": "budget-report.pdf"},
        ],
        [],
    )

    assert [item["document_id"] for item in fused] == ["doc-1", "doc-2"]


def test_qa_retrieve_blocks_filters_by_document_id_and_uses_snippet_content(monkeypatch):
    service = QAService()

    def fake_workspace_search(**kwargs):
        if kwargs.get("group_by_document") is True:
            return {
                "documents": [
                    {"document_id": "doc-1", "score": 0.61},
                    {"document_id": "doc-2", "score": 0.94},
                ]
            }
        if kwargs.get("document_ids") == ["doc-1"]:
            return {
                "results": [
                    {
                        "document_id": "doc-1",
                        "content_snippet": "预算计划摘要",
                        "section": "1.1",
                        "score": 0.61,
                    }
                ]
            }
        return {
            "results": [
                {
                    "document_id": "doc-2",
                    "content_snippet": "预算报告正文",
                    "section": "2.3",
                    "score": 0.94,
                }
            ]
        }

    service.retrieval_service.workspace_search = fake_workspace_search

    blocks = asyncio.run(service._retrieve_blocks("预算", ["doc-2"], top_k=5))

    assert blocks == [
        {
            "doc_id": "doc-2",
            "filename": "",
            "content": "预算报告正文",
            "section": "2.3",
            "score": 0.94,
            "page_number": None,
        }
    ]


def test_qa_retrieve_blocks_uses_workspace_search_fallback_with_document_scope(monkeypatch):
    service = QAService()
    calls = []

    def fake_workspace_search(**kwargs):
        calls.append(kwargs)
        if kwargs.get("group_by_document") is True:
            return {"documents": [{"document_id": "doc-2", "score": 0.91}]}
        return {
            "retrieval_version_used": "metadata_fallback",
            "results": [
                {
                    "document_id": "doc-2",
                    "content_snippet": "金融是货币、信用与资金融通活动的总称。",
                    "score": 0.91,
                }
            ],
        }

    service.retrieval_service.workspace_search = fake_workspace_search

    blocks = asyncio.run(service._retrieve_blocks("什么是金融", ["doc-2"], top_k=5))

    assert calls[0]["query"] == "什么是金融"
    assert calls[0]["document_ids"] == ["doc-2"]
    assert calls[0]["group_by_document"] is True
    assert calls[1]["document_ids"] == ["doc-2"]
    assert calls[1]["group_by_document"] is False
    assert blocks == [
        {
            "doc_id": "doc-2",
            "filename": "",
            "content": "金融是货币、信用与资金融通活动的总称。",
            "section": "",
            "score": 0.91,
            "page_number": None,
        }
    ]


def test_qa_retrieve_blocks_prefers_document_level_narrowing_and_skips_low_value_reader_blocks(monkeypatch):
    service = QAService()
    calls = []

    def fake_workspace_search(**kwargs):
        calls.append(kwargs)
        if kwargs.get("group_by_document") is True:
            return {
                "documents": [
                    {
                        "document_id": "doc-title",
                        "filename": "中国是部金融史.pdf",
                        "score": 0.97,
                    },
                    {
                        "document_id": "doc-other",
                        "filename": "中国银行存款利率.xlsx",
                        "score": 0.55,
                    },
                ]
            }
        if kwargs.get("document_ids") == ["doc-title"]:
            return {
                "results": [
                    {
                        "document_id": "doc-title",
                        "block_id": "doc-title:toc",
                        "content_snippet": "目录\n第一章 此朝无钱胜有钱\n第二章 秦始皇统一了货币吗",
                        "section": "",
                        "score": 0.99,
                    },
                    {
                        "document_id": "doc-title",
                        "block_id": "doc-title:intro",
                        "content_snippet": "当代金融学教学科研的根基是西方经济学。",
                        "section": "序",
                        "score": 0.88,
                    },
                ]
            }
        return {
            "results": [
                {
                    "document_id": "doc-other",
                    "block_id": "doc-other:block-1",
                    "content_snippet": "讨论中国居民金融资产与社会分层。",
                    "section": "5.2",
                    "score": 0.95,
                }
            ]
        }

    service.retrieval_service.workspace_search = fake_workspace_search

    blocks = asyncio.run(service._retrieve_blocks("中国金融史", None, top_k=5))

    assert len(calls) == 3
    assert calls[0]["group_by_document"] is True
    assert calls[1]["group_by_document"] is False
    assert calls[1]["document_ids"] == ["doc-title"]
    assert calls[2]["group_by_document"] is False
    assert calls[2]["document_ids"] == ["doc-other"]
    assert blocks == [
        {
            "doc_id": "doc-title",
            "filename": "",
            "content": "当代金融学教学科研的根基是西方经济学。",
            "section": "序",
            "score": 0.88,
            "page_number": None,
        },
        {
            "doc_id": "doc-other",
            "filename": "",
            "content": "讨论中国居民金融资产与社会分层。",
            "section": "5.2",
            "score": 0.95,
            "page_number": None,
        }
    ]


def test_qa_definition_query_prefers_central_document_and_focus_blocks(monkeypatch):
    service = QAService()

    def fake_workspace_search(**kwargs):
        if kwargs.get("group_by_document") is True:
            return {
                "documents": [
                    {
                        "document_id": "doc-title",
                        "filename": "中国是部金融史.pdf",
                        "classification_result": "金融历史书籍",
                        "score": 0.69,
                    },
                    {
                        "document_id": "doc-other",
                        "filename": "当代中国社会分层.pdf",
                        "classification_result": "社会学书籍",
                        "score": 0.74,
                    },
                ]
            }
        if kwargs.get("document_ids") == ["doc-title"]:
            return {
                "results": [
                    {
                        "document_id": "doc-title",
                        "filename": "中国是部金融史.pdf",
                        "block_id": "doc-title:toc",
                        "content_snippet": "目录\n第一章 此朝无钱胜有钱\n第二章 秦始皇统一了货币吗",
                        "section": "",
                        "score": 0.98,
                    },
                    {
                        "document_id": "doc-title",
                        "filename": "中国是部金融史.pdf",
                        "block_id": "doc-title:intro",
                        "content_snippet": "当代金融学教学科研的根基是西方经济学。",
                        "section": "序",
                        "page_number": 6,
                        "score": 0.74,
                    },
                    {
                        "document_id": "doc-title",
                        "filename": "中国是部金融史.pdf",
                        "block_id": "doc-title:license",
                        "content_snippet": "任何时代金融牌照都是最值钱的东西。",
                        "section": "东晋",
                        "page_number": 149,
                        "score": 0.72,
                    },
                    {
                        "document_id": "doc-title",
                        "filename": "中国是部金融史.pdf",
                        "block_id": "doc-title:random",
                        "content_snippet": "勾践的回应似乎很够意思，你必须和我一起共坐江山。",
                        "section": "越国",
                        "page_number": 28,
                        "score": 0.93,
                    },
                ]
            }
        return {
            "results": [
                {
                    "document_id": "doc-other",
                    "filename": "当代中国社会分层.pdf",
                    "block_id": "doc-other:product",
                    "content_snippet": "所谓金融理财产品，主要指基金、股票、期货、期权和有价证券等。",
                    "section": "19.1",
                    "page_number": 417,
                    "score": 0.92,
                }
            ]
        }

    service.retrieval_service.workspace_search = fake_workspace_search

    blocks = asyncio.run(service._retrieve_blocks("什么是金融", None, top_k=3))

    assert [block["doc_id"] for block in blocks[:2]] == ["doc-title", "doc-title"]
    assert blocks[0]["content"] == "当代金融学教学科研的根基是西方经济学。"
    assert blocks[1]["content"] == "任何时代金融牌照都是最值钱的东西。"
    assert all("勾践" not in block["content"] for block in blocks)


def test_qa_definition_query_normalizes_ocr_focus_terms(monkeypatch):
    service = QAService()

    def fake_workspace_search(**kwargs):
        if kwargs.get("group_by_document") is True:
            return {
                "documents": [
                    {
                        "document_id": "doc-title",
                        "filename": "中国是部金融史.pdf",
                        "classification_result": "金融历史书籍",
                        "score": 0.55,
                    },
                    {
                        "document_id": "doc-other",
                        "filename": "当代中国社会分层.pdf",
                        "classification_result": "社会学书籍",
                        "score": 0.73,
                    },
                ]
            }
        if kwargs.get("document_ids") == ["doc-title"]:
            return {
                "results": [
                    {
                        "document_id": "doc-title",
                        "filename": "中国是部金融史.pdf",
                        "block_id": "doc-title:intro",
                        "content_snippet": "当代⾦融学教学科研的根基是⻄⽅经济学。",
                        "section": "序",
                        "score": 0.56,
                    }
                ]
            }
        return {
            "results": [
                {
                    "document_id": "doc-other",
                    "filename": "当代中国社会分层.pdf",
                    "block_id": "doc-other:product",
                    "content_snippet": "所谓金融理财产品，主要指基金、股票、期货、期权和有价证券等。",
                    "section": "19.1",
                    "score": 0.74,
                }
            ]
        }

    service.retrieval_service.workspace_search = fake_workspace_search

    blocks = asyncio.run(service._retrieve_blocks("什么是金融", None, top_k=2))

    assert blocks[0]["doc_id"] == "doc-title"
    assert "⾦融学" in blocks[0]["content"]


def test_qa_chain_build_context_uses_human_readable_source_labels():
    service = QAService()

    context = service.qa_chain.build_context(
        [
            {
                "doc_id": "doc-2",
                "filename": "预算报告.pdf",
                "content": "预算报告正文",
                "section": "2.3",
                "page_number": 5,
            }
        ]
    )

    assert "[doc-2 | 预算报告.pdf §2.3 P5]" in context
    assert "预算报告正文" in context


def test_qa_answer_persists_session_and_returns_session_id(monkeypatch, tmp_path: Path):
    service = QAService()
    service.qa_session_repo = _create_qa_repo(tmp_path)

    def fake_workspace_search(**kwargs):
        if kwargs.get("group_by_document") is True:
            return {"documents": [{"document_id": "doc-2", "score": 0.94}]}
        return {
            "results": [
                {
                    "document_id": "doc-2",
                    "content_snippet": "预算报告正文",
                    "section": "2.3",
                    "score": 0.94,
                }
            ]
        }

    async def fake_call(*args, **kwargs):
        return LLMResponse(content="结论 [doc-2 §2.3]", tokens_used=12, model="fake")

    service.retrieval_service.workspace_search = fake_workspace_search
    service.llm_gateway.call = fake_call

    result = asyncio.run(service.answer("预算是什么", ["doc-2"], top_k=5, session_id="sess-1"))

    assert result["session_id"] == "sess-1"
    assert result["citations"] == [{"doc_id": "doc-2", "section": "2.3", "type": "inline"}]
    assert service.qa_session_repo.get("sess-1")["doc_ids"] == ["doc-2"]


def test_list_qa_sessions_returns_recent_sessions_without_doc_filter(tmp_path: Path):
    repo = _create_qa_repo(tmp_path)
    repo.save("预算是什么", ["doc-1"], "答复1", [])
    repo.save("合同是什么", ["doc-2"], "答复2", [])
    qa_api.qa_service.qa_session_repo = repo

    body = asyncio.run(qa_api.list_qa_sessions(doc_id=None, limit=20))

    assert body["code"] == 200
    assert body["data"]["total"] == 2
    assert len(body["data"]["items"]) == 2


def test_streaming_qa_completion_frame_contains_session_id(monkeypatch):
    async def fake_answer_stream(*args, **kwargs):
        yield "片段一"
        yield "片段二"

    qa_api.qa_service.answer_stream = fake_answer_stream

    response = asyncio.run(
        qa_api.answer_question_stream(
            qa_api.QARequest(query="预算", doc_ids=["doc-1"], session_id="sess-1")
        )
    )
    stream_text = asyncio.run(_read_streaming_response(response))
    done_frames = [
        frame for frame in stream_text.split("\n\n")
        if '"status": "complete"' in frame
    ]

    assert len(done_frames) == 1
    payload = json.loads(done_frames[0].split("data: ", 1)[1])
    assert payload["session_id"] == "sess-1"
