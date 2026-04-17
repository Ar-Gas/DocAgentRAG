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

    async def fake_search_with_analysis(*args, **kwargs):
        return {
            "results": [
                {
                    "document_id": "doc-1",
                    "content_snippet": "预算计划摘要",
                    "section": "1.1",
                    "score": 0.61,
                },
                {
                    "document_id": "doc-2",
                    "content_snippet": "预算报告正文",
                    "section": "2.3",
                    "score": 0.94,
                },
            ]
        }

    service.retrieval_service.search_with_analysis = fake_search_with_analysis

    blocks = asyncio.run(service._retrieve_blocks("预算", ["doc-2"], top_k=5))

    assert blocks == [
        {
            "doc_id": "doc-2",
            "content": "预算报告正文",
            "section": "2.3",
            "score": 0.94,
        }
    ]


def test_qa_answer_persists_session_and_returns_session_id(monkeypatch, tmp_path: Path):
    service = QAService()
    service.qa_session_repo = _create_qa_repo(tmp_path)

    async def fake_search_with_analysis(*args, **kwargs):
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

    service.retrieval_service.search_with_analysis = fake_search_with_analysis
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
