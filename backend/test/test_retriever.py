#!/usr/bin/env python3
import os
import sys
import unittest
from unittest import mock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.retriever import (  # noqa: E402
    batch_search_documents,
    get_document_by_id,
    get_document_stats,
    get_ready_block_document_ids,
    hybrid_search,
    keyword_search,
    multimodal_search,
    search_block_documents,
    search_documents,
)


def _build_block_payload(entries=None):
    entries = entries or [
        {
            "document_id": "doc-1",
            "filename": "budget-report.pdf",
            "path": "/docs/budget-report.pdf",
            "file_type": ".pdf",
            "classification_result": "财务",
            "created_at_iso": "2026-03-20T10:00:00",
            "parser_name": "pdf",
            "extraction_status": "ready",
            "preview_content": "预算审批流程和采购说明",
            "file_available": True,
            "block_id": "doc-1:block-v1:0",
            "block_index": 0,
            "block_type": "paragraph",
            "snippet": "预算审批流程和采购说明",
            "heading_path": ["预算管理"],
            "page_number": 1,
            "score": 0.94,
            "match_reason": "heading + body match",
        }
    ]

    documents = []
    results = []
    for index, item in enumerate(entries):
        document_id = item["document_id"]
        block_id = item.get("block_id") or f"{document_id}:block-v1:{item.get('block_index', index)}"
        block_index = item.get("block_index", index)
        snippet = item.get("snippet", "")
        score = item.get("score", 0.0)
        documents.append(
            {
                "document_id": document_id,
                "filename": item.get("filename", ""),
                "path": item.get("path", ""),
                "file_type": item.get("file_type", ""),
                "classification_result": item.get("classification_result"),
                "created_at_iso": item.get("created_at_iso"),
                "parser_name": item.get("parser_name"),
                "extraction_status": item.get("extraction_status"),
                "preview_content": item.get("preview_content", snippet),
                "file_available": item.get("file_available", False),
                "score": score,
                "best_similarity": score,
                "hit_count": 1,
                "result_count": 1,
                "best_excerpt": snippet,
                "best_block_id": block_id,
                "matched_terms": [],
                "evidence_blocks": [
                    {
                        "block_id": block_id,
                        "block_index": block_index,
                        "block_type": item.get("block_type", "paragraph"),
                        "snippet": snippet,
                        "heading_path": item.get("heading_path", []),
                        "page_number": item.get("page_number"),
                        "score": score,
                        "match_reason": item.get("match_reason", ""),
                    }
                ],
                "top_segments": [],
                "results": [],
            }
        )
        results.append(
            {
                "document_id": document_id,
                "block_id": block_id,
                "block_index": block_index,
                "block_type": item.get("block_type", "paragraph"),
                "snippet": snippet,
                "heading_path": item.get("heading_path", []),
                "page_number": item.get("page_number"),
                "score": score,
                "match_reason": item.get("match_reason", ""),
            }
        )

    return {
        "documents": documents,
        "results": results,
        "meta": {
            "fallback_used": False,
            "candidate_count": len(results),
            "expanded_queries": [],
        },
    }


class TestRetriever(unittest.TestCase):
    def test_search_documents_invalid_params(self):
        self.assertEqual(search_documents("", limit=10), [])
        self.assertEqual(search_documents(123, limit=10), [])
        self.assertEqual(search_documents("预算", limit=0), [])
        self.assertEqual(search_documents("预算", limit=-1), [])

    @mock.patch("utils.retriever.get_all_documents")
    def test_get_ready_block_document_ids_accepts_classification_id_filter(
        self,
        mock_get_all_documents,
    ):
        mock_get_all_documents.return_value = [
            {
                "id": "doc-1",
                "filename": "offer-guide.docx",
                "file_type": ".docx",
                "classification_result": "Offer审批",
                "classification_id": "hr.offer_approval",
                "block_index_status": "ready",
                "created_at_iso": "2026-03-20T10:00:00",
            },
            {
                "id": "doc-2",
                "filename": "budget-guide.docx",
                "file_type": ".docx",
                "classification_result": "预算制度",
                "classification_id": "finance.budget_policy",
                "block_index_status": "ready",
                "created_at_iso": "2026-03-20T10:00:00",
            },
        ]

        ready_ids = get_ready_block_document_ids(classification="hr.offer_approval")

        self.assertEqual(ready_ids, {"doc-1"})

    @mock.patch("utils.retriever.search_block_documents")
    @mock.patch("utils.retriever.get_ready_block_document_ids")
    def test_search_documents_uses_block_vector_mode_and_normalizes_results(
        self,
        mock_get_ready_block_document_ids,
        mock_search_block_documents,
    ):
        mock_get_ready_block_document_ids.return_value = {"doc-1"}
        mock_search_block_documents.return_value = _build_block_payload()

        results = search_documents("预算", limit=2, use_rerank=False, file_types=["pdf"])

        self.assertEqual(
            mock_get_ready_block_document_ids.call_args.kwargs,
            {
                "file_types": ["pdf"],
                "filename": None,
                "classification": None,
                "date_from": None,
                "date_to": None,
            },
        )
        self.assertEqual(mock_search_block_documents.call_args.kwargs["mode"], "vector")
        self.assertEqual(mock_search_block_documents.call_args.kwargs["alpha"], 1.0)
        self.assertEqual(mock_search_block_documents.call_args.kwargs["ready_document_ids"], {"doc-1"})
        self.assertFalse(mock_search_block_documents.call_args.kwargs["use_rerank"])
        self.assertFalse(mock_search_block_documents.call_args.kwargs["use_llm_rerank"])
        self.assertFalse(mock_search_block_documents.call_args.kwargs["group_by_document"])
        self.assertEqual(results[0]["document_id"], "doc-1")
        self.assertEqual(results[0]["content_snippet"], "预算审批流程和采购说明")
        self.assertEqual(results[0]["similarity"], 0.94)
        self.assertEqual(results[0]["chunk_index"], 0)
        self.assertEqual(results[0]["block_id"], "doc-1:block-v1:0")

    @mock.patch("utils.retriever.rerank_documents")
    @mock.patch("utils.retriever.search_block_documents")
    @mock.patch("utils.retriever.get_ready_block_document_ids")
    def test_search_documents_can_rerank_block_results(
        self,
        mock_get_ready_block_document_ids,
        mock_search_block_documents,
        mock_rerank_documents,
    ):
        mock_get_ready_block_document_ids.return_value = {"doc-1", "doc-2"}
        mock_search_block_documents.return_value = _build_block_payload(
            [
                {
                    "document_id": "doc-1",
                    "filename": "budget-report.pdf",
                    "path": "/docs/budget-report.pdf",
                    "file_type": ".pdf",
                    "snippet": "预算审批流程和采购说明",
                    "score": 0.74,
                    "block_id": "doc-1:block-v1:0",
                    "block_index": 0,
                },
                {
                    "document_id": "doc-2",
                    "filename": "travel-policy.docx",
                    "path": "/docs/travel-policy.docx",
                    "file_type": ".docx",
                    "snippet": "差旅报销标准说明",
                    "score": 0.71,
                    "block_id": "doc-2:block-v1:3",
                    "block_index": 3,
                },
            ]
        )
        mock_rerank_documents.side_effect = lambda query, results, top_k: [
            {**results[1], "similarity": 0.99},
            {**results[0], "similarity": 0.52},
        ]

        results = search_documents("报销", limit=2, use_rerank=True)

        self.assertEqual(mock_rerank_documents.call_count, 1)
        self.assertEqual(mock_rerank_documents.call_args.kwargs["top_k"], 2)
        self.assertEqual(results[0]["document_id"], "doc-2")
        self.assertEqual(results[0]["similarity"], 0.99)

    @mock.patch("utils.retriever.search_block_documents")
    @mock.patch("utils.retriever.get_ready_block_document_ids")
    def test_keyword_search_merges_file_type_filters_and_prioritizes_exact_match(
        self,
        mock_get_ready_block_document_ids,
        mock_search_block_documents,
    ):
        mock_get_ready_block_document_ids.return_value = {"doc-1", "doc-2"}
        mock_search_block_documents.return_value = _build_block_payload(
            [
                {
                    "document_id": "doc-2",
                    "filename": "budget-summary.docx",
                    "path": "/docs/budget-summary.docx",
                    "file_type": ".docx",
                    "snippet": "预算流程概览",
                    "score": 0.93,
                    "block_id": "doc-2:block-v1:1",
                    "block_index": 1,
                },
                {
                    "document_id": "doc-1",
                    "filename": "budget-approval.pdf",
                    "path": "/docs/budget-approval.pdf",
                    "file_type": ".pdf",
                    "snippet": "预算审批流程和采购说明",
                    "score": 0.72,
                    "block_id": "doc-1:block-v1:0",
                    "block_index": 0,
                },
            ]
        )

        results = keyword_search('"预算审批" filetype:pdf', limit=2, file_types=["word"])

        self.assertEqual(mock_search_block_documents.call_args.kwargs["mode"], "keyword")
        self.assertEqual(set(mock_search_block_documents.call_args.kwargs["file_types"]), {"word", "pdf"})
        self.assertEqual(set(mock_get_ready_block_document_ids.call_args.kwargs["file_types"]), {"word", "pdf"})
        self.assertEqual(results[0]["document_id"], "doc-1")
        self.assertTrue(results[0]["has_exact_match"])
        self.assertFalse(results[1]["has_exact_match"])

    @mock.patch("utils.retriever.search_block_documents")
    @mock.patch("utils.retriever.get_ready_block_document_ids")
    def test_hybrid_search_uses_block_helper_and_preserves_alpha(
        self,
        mock_get_ready_block_document_ids,
        mock_search_block_documents,
    ):
        mock_get_ready_block_document_ids.return_value = {"doc-1"}
        mock_search_block_documents.return_value = _build_block_payload()

        results = hybrid_search("预算", limit=3, alpha=0.35, use_rerank=False, file_types=["pdf"])

        self.assertEqual(mock_search_block_documents.call_args.kwargs["mode"], "hybrid")
        self.assertEqual(mock_search_block_documents.call_args.kwargs["alpha"], 0.35)
        self.assertEqual(results[0]["document_id"], "doc-1")
        self.assertEqual(results[0]["similarity"], 0.94)

    def test_batch_search_documents_invalid_params(self):
        self.assertEqual(batch_search_documents("不是列表", limit=5), [])
        self.assertEqual(batch_search_documents([], limit=5), [])
        self.assertEqual(batch_search_documents(["查询1"], limit=0), [])

    @mock.patch("utils.retriever.search_documents")
    def test_batch_search_documents_delegates_each_query(self, mock_search_documents):
        mock_search_documents.side_effect = [
            [{"document_id": "doc-1", "content_snippet": "预算"}],
            [{"document_id": "doc-2", "content_snippet": "合同"}],
        ]

        results = batch_search_documents(["预算", "合同"], limit=2)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0][0]["document_id"], "doc-1")
        self.assertEqual(results[1][0]["document_id"], "doc-2")
        self.assertEqual(
            mock_search_documents.call_args_list,
            [
                mock.call("预算", limit=2, use_rerank=False, file_types=None),
                mock.call("合同", limit=2, use_rerank=False, file_types=None),
            ],
        )

    @mock.patch("utils.retriever.get_block_collection")
    def test_search_block_documents_returns_empty_when_ready_documents_are_missing(self, mock_get_block_collection):
        mock_get_block_collection.return_value = mock.MagicMock()

        payload = search_block_documents(
            query="预算",
            mode="hybrid",
            limit=5,
            alpha=0.5,
            use_rerank=False,
            use_llm_rerank=False,
            file_types=None,
            classification=None,
            date_from=None,
            date_to=None,
            ready_document_ids=set(),
            group_by_document=True,
        )

        self.assertEqual(payload, {"documents": [], "results": [], "meta": {"fallback_used": False}})

    @mock.patch("utils.retriever.get_all_documents")
    @mock.patch("utils.retriever.get_block_collection")
    def test_search_block_documents_returns_document_evidence_without_legacy_fallback(
        self,
        mock_get_block_collection,
        mock_get_all_documents,
    ):
        fake_collection = mock.MagicMock()
        fake_collection.get.return_value = {
            "ids": ["doc-1:block-v1:0"],
            "documents": ["预算审批流程和采购说明"],
            "metadatas": [
                {
                    "document_id": "doc-1",
                    "filename": "budget-report.pdf",
                    "file_type": ".pdf",
                    "block_id": "doc-1:block-v1:0",
                    "block_index": 0,
                    "block_type": "paragraph",
                    "heading_path": '["预算管理"]',
                    "page_number": 3,
                }
            ],
        }
        mock_get_block_collection.return_value = fake_collection
        mock_get_all_documents.return_value = [
            {
                "id": "doc-1",
                "filename": "budget-report.pdf",
                "filepath": "/docs/budget-report.pdf",
                "file_type": ".pdf",
                "classification_result": "财务",
                "created_at_iso": "2026-03-20T10:00:00",
                "preview_content": "预算审批流程和采购说明",
                "block_index_status": "ready",
            }
        ]

        payload = search_block_documents(
            query="",
            mode="hybrid",
            limit=10,
            alpha=0.5,
            use_rerank=False,
            use_llm_rerank=False,
            file_types=None,
            classification=None,
            date_from=None,
            date_to=None,
            ready_document_ids={"doc-1"},
            group_by_document=True,
        )

        self.assertEqual(payload["documents"][0]["document_id"], "doc-1")
        self.assertEqual(payload["documents"][0]["best_block_id"], "doc-1:block-v1:0")
        self.assertEqual(payload["documents"][0]["evidence_blocks"][0]["heading_path"], ["预算管理"])
        self.assertEqual(payload["results"][0]["block_id"], "doc-1:block-v1:0")

    def test_get_document_by_id_invalid_params(self):
        self.assertIsNone(get_document_by_id(""))
        self.assertIsNone(get_document_by_id(123))

    @mock.patch("utils.retriever.get_block_collection")
    def test_get_document_by_id_reads_from_block_collection_and_aliases_chunk_index(self, mock_get_block_collection):
        fake_collection = mock.MagicMock()
        fake_collection.get.return_value = {
            "ids": ["doc-1:block-v1:1", "doc-1:block-v1:0"],
            "documents": ["第二段", "第一段"],
            "metadatas": [
                {"document_id": "doc-1", "block_index": 1, "heading_path": '["第二节"]'},
                {"document_id": "doc-1", "block_index": 0, "heading_path": '["第一节"]'},
            ],
        }
        mock_get_block_collection.return_value = fake_collection

        result = get_document_by_id("doc-1")

        fake_collection.get.assert_called_once_with(where={"document_id": "doc-1"}, include=["documents", "metadatas"])
        self.assertEqual(result["ids"][0], "doc-1:block-v1:0")
        self.assertEqual(result["chunks"][0], "第一段")
        self.assertEqual(result["metadatas"][0]["chunk_index"], 0)
        self.assertEqual(result["metadatas"][1]["chunk_index"], 1)

    @mock.patch("utils.retriever.get_block_collection")
    def test_get_document_stats_counts_document_blocks(self, mock_get_block_collection):
        fake_collection = mock.MagicMock()
        fake_collection.count.return_value = 3
        fake_collection.get.side_effect = [
            {
                "metadatas": [
                    {"document_id": "doc-1", "file_type": ".pdf"},
                    {"document_id": "doc-1", "file_type": ".pdf"},
                    {"document_id": "doc-2", "file_type": ".docx"},
                ]
            }
        ]
        mock_get_block_collection.return_value = fake_collection

        stats = get_document_stats()

        self.assertEqual(stats["total_chunks"], 3)
        self.assertEqual(stats["vector_indexed_documents"], 2)
        self.assertEqual(stats["file_types"], {".pdf": 2, ".docx": 1})
        fake_collection.get.assert_called_once_with(limit=1000, offset=0, include=["metadatas"])

    @mock.patch("utils.retriever.get_block_collection")
    def test_get_document_stats_collection_unavailable(self, mock_get_block_collection):
        mock_get_block_collection.return_value = None

        stats = get_document_stats()

        self.assertEqual(stats, {"total_chunks": 0, "vector_indexed_documents": 0, "file_types": {}})

    @mock.patch("utils.retriever.get_query_embedding")
    @mock.patch("utils.retriever.get_ready_block_document_ids")
    @mock.patch("utils.retriever.get_block_collection")
    def test_multimodal_search_queries_document_blocks(
        self,
        mock_get_block_collection,
        mock_get_ready_block_document_ids,
        mock_get_query_embedding,
    ):
        fake_collection = mock.MagicMock()
        fake_collection.query.return_value = {
            "documents": [["预算审批流程和采购说明", "孤儿结果"]],
            "metadatas": [[
                {
                    "document_id": "doc-1",
                    "filename": "budget-report.pdf",
                    "filepath": "/docs/budget-report.pdf",
                    "file_type": ".pdf",
                    "block_id": "doc-1:block-v1:0",
                    "block_index": 0,
                },
                {
                    "document_id": "ghost",
                    "filename": "ghost.pdf",
                    "filepath": "/docs/ghost.pdf",
                    "file_type": ".pdf",
                    "block_id": "ghost:block-v1:0",
                    "block_index": 0,
                },
            ]],
            "distances": [[0.05, 0.01]],
        }
        mock_get_block_collection.return_value = fake_collection
        mock_get_ready_block_document_ids.return_value = {"doc-1"}
        mock_get_query_embedding.return_value = [0.1, 0.2, 0.3]

        results = multimodal_search("预算", image_url="https://example.com/sample.png", limit=2, file_types=["pdf"])

        self.assertEqual(mock_get_ready_block_document_ids.call_args.kwargs["file_types"], ["pdf"])
        self.assertEqual(fake_collection.query.call_args.kwargs["n_results"], 10)
        self.assertEqual(results, [
            {
                "document_id": "doc-1",
                "filename": "budget-report.pdf",
                "path": "/docs/budget-report.pdf",
                "file_type": ".pdf",
                "similarity": 0.95,
                "content_snippet": "预算审批流程和采购说明",
                "chunk_index": 0,
                "block_id": "doc-1:block-v1:0",
                "block_index": 0,
                "embedding_model": mock.ANY,
                "multimodal_query": True,
            }
        ])

    @mock.patch("utils.retriever.search_documents")
    @mock.patch("utils.retriever.get_query_embedding")
    def test_multimodal_search_falls_back_to_block_vector_search_when_embedding_missing(
        self,
        mock_get_query_embedding,
        mock_search_documents,
    ):
        mock_get_query_embedding.return_value = None
        mock_search_documents.return_value = [{"document_id": "doc-1", "content_snippet": "预算审批"}]

        results = multimodal_search("预算", limit=1, file_types=["pdf"])

        self.assertEqual(results, [{"document_id": "doc-1", "content_snippet": "预算审批"}])
        mock_search_documents.assert_called_once_with("预算", limit=1, file_types=["pdf"])


if __name__ == "__main__":
    unittest.main()
