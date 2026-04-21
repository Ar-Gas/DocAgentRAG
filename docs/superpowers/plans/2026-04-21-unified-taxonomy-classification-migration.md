# Unified Taxonomy Classification Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce `taxonomy_v2` with broader hierarchical labels, version-aware storage, and compatibility mapping while keeping current classification APIs and `/documents` rendering stable.

**Architecture:** Add the new taxonomy beside the current one, persist versioned leaf metadata in SQLite, and refactor `TaxonomyClassifier` into small helper modules that route by domain, score in-domain candidates, and reserve raw `no_match` for abnormal content only. Keep the existing display DTO stable by normalizing both old and new assignments through a compatibility layer.

**Tech Stack:** FastAPI, sqlite3, pytest, Vue 3, Vitest

---

## File Structure

**Files:**
- Create: `backend/app/domain/taxonomy/unified_document_taxonomy.py`
- Create: `backend/app/services/classification_input_builder.py`
- Create: `backend/app/services/taxonomy_domain_router.py`
- Create: `backend/app/services/taxonomy_candidate_resolver.py`
- Create: `backend/app/services/taxonomy_label_selector.py`
- Create: `backend/app/services/taxonomy_review_policy.py`
- Create: `backend/app/services/taxonomy_compatibility.py`
- Create: `backend/test/test_taxonomy_v2_storage.py`
- Create: `backend/test/test_unified_document_taxonomy.py`
- Create: `backend/test/test_taxonomy_classifier_v2.py`
- Create: `backend/test/test_classification_service_v2.py`
- Modify: `backend/app/domain/taxonomy/__init__.py`
- Modify: `backend/app/infra/metadata_store.py`
- Modify: `backend/app/infra/repositories/document_repository.py`
- Modify: `backend/app/schemas/classification.py`
- Modify: `backend/app/services/taxonomy_classifier.py`
- Modify: `backend/app/services/classification_service.py`
- Modify: `backend/migrations/add_taxonomy_fields.py`
- Modify: `backend/migrations/backfill_taxonomy.py`
- Modify: `frontend/docagent-frontend/src/components/FileList.vue`
- Modify: `frontend/docagent-frontend/src/components/__tests__/FileList.spec.js`

---

### Task 1: Persist Taxonomy v2 Metadata Without Breaking Current Document Rows

**Files:**
- Create: `backend/test/test_taxonomy_v2_storage.py`
- Modify: `backend/app/infra/metadata_store.py`
- Modify: `backend/app/infra/repositories/document_repository.py`
- Modify: `backend/migrations/add_taxonomy_fields.py`

- [ ] **Step 1: Write the failing storage contract test**

Create `backend/test/test_taxonomy_v2_storage.py` with:

```python
import json
from pathlib import Path

from app.infra.metadata_store import DocumentMetadataStore


def test_metadata_store_round_trips_taxonomy_v2_fields(tmp_path: Path):
    store = DocumentMetadataStore(db_path=tmp_path / "docagent.db", data_dir=tmp_path)

    store.upsert_document(
        {
            "id": "doc-1",
            "filename": "ops-manual.pdf",
            "filepath": str(tmp_path / "ops-manual.pdf"),
            "file_type": ".pdf",
            "classification_result": "运维手册",
            "classification_id": "tech.operations_manual",
            "classification_leaf_id": "tech.operations_manual",
            "classification_path": ["技术文档", "运维体系", "运维手册"],
            "classification_domain": "技术文档",
            "classification_score": 0.91,
            "classification_confidence": 0.91,
            "classification_source": "llm",
            "classification_review_status": "accepted",
            "classification_issue_code": None,
            "taxonomy_version": "taxonomy_v2",
        }
    )

    row = store.get_document("doc-1")

    assert row["classification_leaf_id"] == "tech.operations_manual"
    assert row["classification_domain"] == "技术文档"
    assert row["classification_confidence"] == 0.91
    assert row["taxonomy_version"] == "taxonomy_v2"
    payload = row["payload"]
    assert payload["classification_leaf_id"] == "tech.operations_manual"
    assert payload["taxonomy_version"] == "taxonomy_v2"


def test_add_taxonomy_fields_migration_adds_v2_columns(tmp_path: Path):
    from backend.migrations import add_taxonomy_fields
    import sqlite3

    db_path = tmp_path / "docagent.db"
    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute(
            """
            CREATE TABLE documents (
                id TEXT PRIMARY KEY,
                filename TEXT,
                classification_result TEXT,
                payload TEXT
            )
            """
        )
        connection.execute(
            "INSERT INTO documents (id, filename, classification_result, payload) VALUES (?, ?, ?, ?)",
            ("doc-1", "ops-manual.pdf", "运维手册", json.dumps({"id": "doc-1"}, ensure_ascii=False)),
        )
        connection.commit()
    finally:
        connection.close()

    summary = add_taxonomy_fields.migrate(db_path=db_path)

    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    try:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(documents)").fetchall()
        }
    finally:
        connection.close()

    assert summary["document_count"] == 1
    assert {
        "classification_leaf_id",
        "classification_domain",
        "classification_confidence",
        "taxonomy_version",
    }.issubset(columns)
```

- [ ] **Step 2: Run the storage tests and verify they fail**

Run: `cd backend && python -m pytest test/test_taxonomy_v2_storage.py -v`
Expected: FAIL because the store and migration do not persist `classification_leaf_id`, `classification_domain`, `classification_confidence`, or `taxonomy_version` yet.

- [ ] **Step 3: Implement additive v2 storage fields and migration support**

Update `backend/migrations/add_taxonomy_fields.py` by extending `COLUMN_DEFINITIONS` with:

```python
COLUMN_DEFINITIONS = {
    "classification_id": "TEXT DEFAULT NULL",
    "classification_path": "TEXT DEFAULT NULL",
    "classification_score": "REAL DEFAULT 0.0",
    "classification_source": "TEXT DEFAULT NULL",
    "classification_candidates": "TEXT DEFAULT NULL",
    "classification_review_status": "TEXT DEFAULT NULL",
    "classification_issue_code": "TEXT DEFAULT NULL",
    "classification_leaf_id": "TEXT DEFAULT NULL",
    "classification_domain": "TEXT DEFAULT NULL",
    "classification_confidence": "REAL DEFAULT 0.0",
    "taxonomy_version": "TEXT DEFAULT 'taxonomy_v1'",
    "ingest_status": "TEXT DEFAULT NULL",
    "ingest_error": "TEXT DEFAULT NULL",
    "lightrag_track_id": "TEXT DEFAULT NULL",
    "lightrag_doc_id": "TEXT DEFAULT NULL",
    "last_status_sync_at": "TEXT DEFAULT NULL",
    "local_index_status": "TEXT DEFAULT NULL",
    "local_index_error": "TEXT DEFAULT NULL",
}
```

Update the `documents` table definition in `backend/app/infra/metadata_store.py` so it includes:

```python
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    filepath TEXT,
    file_type TEXT,
    classification_result TEXT,
    classification_id TEXT,
    classification_leaf_id TEXT,
    classification_path TEXT,
    classification_domain TEXT,
    classification_score REAL,
    classification_confidence REAL,
    classification_source TEXT,
    classification_candidates TEXT,
    classification_review_status TEXT,
    classification_issue_code TEXT,
    taxonomy_version TEXT DEFAULT 'taxonomy_v1',
    ingest_status TEXT,
    ingest_error TEXT,
    lightrag_track_id TEXT,
    lightrag_doc_id TEXT,
    last_status_sync_at TEXT,
    local_index_status TEXT,
    local_index_error TEXT,
    created_at REAL,
    created_at_iso TEXT,
    updated_at TEXT,
    payload TEXT NOT NULL
)
```

Update `_serialize_doc()` and the row-to-payload path in `backend/app/infra/metadata_store.py` so both structured columns and `payload` carry:

```python
{
    "classification_leaf_id": payload.get("classification_leaf_id"),
    "classification_domain": payload.get("classification_domain"),
    "classification_confidence": float(payload.get("classification_confidence") or 0.0),
    "taxonomy_version": payload.get("taxonomy_version") or "taxonomy_v1",
}
```

Update `backend/app/infra/repositories/document_repository.py` with a dedicated helper:

```python
def update_classification_assignment(self, document_id: str, assignment: Dict[str, Any]) -> bool:
    return self._store.update_document(document_id, assignment)
```

- [ ] **Step 4: Re-run the storage tests**

Run: `cd backend && python -m pytest test/test_taxonomy_v2_storage.py -v`
Expected: PASS.

- [ ] **Step 5: Commit the storage changes**

```bash
git add backend/app/infra/metadata_store.py backend/app/infra/repositories/document_repository.py backend/migrations/add_taxonomy_fields.py backend/test/test_taxonomy_v2_storage.py
git commit -m "feat: persist taxonomy v2 metadata"
```

### Task 2: Add A Broad Unified Taxonomy Catalog With Stable Leaf Metadata

**Files:**
- Create: `backend/app/domain/taxonomy/unified_document_taxonomy.py`
- Modify: `backend/app/domain/taxonomy/__init__.py`
- Create: `backend/test/test_unified_document_taxonomy.py`

- [ ] **Step 1: Write the failing taxonomy catalog tests**

Create `backend/test/test_unified_document_taxonomy.py` with:

```python
from app.domain.taxonomy.unified_document_taxonomy import (
    get_all_labels,
    get_domain_fallback,
    get_label_by_id,
    search_by_keyword,
)


def test_unified_taxonomy_exposes_broad_domains_and_fallbacks():
    labels = get_all_labels()
    label_ids = {label["id"] for label in labels}

    assert "office.general_material" in label_ids
    assert "tech.general_material" in label_ids
    assert "books.general_book" in label_ids
    assert "research.general_report" in label_ids
    assert get_domain_fallback("技术文档")["id"] == "tech.general_material"


def test_unified_taxonomy_can_lookup_by_alias_and_keyword():
    label = get_label_by_id("tech.operations_manual")
    assert label["path"] == ["技术文档", "运维体系", "运维手册"]

    matches = search_by_keyword(
        "值班流程、故障处理、巡检和变更窗口",
        filename_text="生产运维手册.pdf",
        top_k=3,
    )

    assert matches[0][0]["id"] == "tech.operations_manual"
    assert matches[0][1] > 0


def test_unified_taxonomy_routes_bookish_titles_into_book_domain():
    matches = search_by_keyword(
        "本书系统讲解 C++ 与泛型编程",
        filename_text="modern-cpp-tutorial-zh-cn.pdf",
        top_k=5,
    )

    assert matches[0][0]["id"] == "books.programming_book"
```

- [ ] **Step 2: Run the taxonomy catalog tests and verify they fail**

Run: `cd backend && python -m pytest test/test_unified_document_taxonomy.py -v`
Expected: FAIL because `unified_document_taxonomy.py` does not exist yet.

- [ ] **Step 3: Implement the unified taxonomy module and export it**

Create `backend/app/domain/taxonomy/unified_document_taxonomy.py` with the catalog and helpers:

```python
from __future__ import annotations

from collections import defaultdict


LEAF_LABELS = [
    {
        "id": "office.work_report",
        "path": ["办公文档", "汇报材料", "工作汇报"],
        "label": "工作汇报",
        "aliases": ["工作总结", "工作复盘", "汇报材料"],
        "keywords": ["汇报", "复盘", "总结", "周报", "月报", "季度"],
        "negative_keywords": ["教材", "小说"],
        "file_types": [".pdf", ".docx", ".pptx"],
        "fallback_rank": 90,
    },
    {
        "id": "office.meeting_minutes",
        "path": ["办公文档", "会议材料", "会议纪要"],
        "label": "会议纪要",
        "aliases": ["会议记录"],
        "keywords": ["会议纪要", "决议", "参会", "议题", "会议记录"],
        "negative_keywords": [],
        "file_types": [".docx", ".pdf"],
        "fallback_rank": 90,
    },
    {
        "id": "office.policy",
        "path": ["办公文档", "制度流程", "管理制度"],
        "label": "管理制度",
        "aliases": ["制度文件", "规章制度"],
        "keywords": ["制度", "规范", "流程", "管理办法", "细则"],
        "negative_keywords": [],
        "file_types": [".pdf", ".docx"],
        "fallback_rank": 90,
    },
    {
        "id": "office.general_material",
        "path": ["办公文档", "综合办公", "通用办公材料"],
        "label": "通用办公材料",
        "aliases": ["综合办公材料"],
        "keywords": ["通知", "附件", "材料", "模板"],
        "negative_keywords": [],
        "file_types": [".pdf", ".docx", ".pptx", ".xlsx"],
        "fallback_rank": 10,
    },
    {
        "id": "tech.architecture_design",
        "path": ["技术文档", "软件工程", "架构设计"],
        "label": "架构设计",
        "aliases": ["系统架构", "架构方案"],
        "keywords": ["架构", "模块设计", "系统设计", "架构设计"],
        "negative_keywords": ["招聘"],
        "file_types": [".pdf", ".md", ".docx"],
        "fallback_rank": 90,
    },
    {
        "id": "tech.operations_manual",
        "path": ["技术文档", "运维体系", "运维手册"],
        "label": "运维手册",
        "aliases": ["运维指南", "运行手册", "runbook"],
        "keywords": ["巡检", "值班", "告警", "故障", "变更", "运维"],
        "negative_keywords": [],
        "file_types": [".pdf", ".docx", ".md"],
        "fallback_rank": 90,
    },
    {
        "id": "tech.development_guide",
        "path": ["技术文档", "开发实践", "开发手册"],
        "label": "开发手册",
        "aliases": ["开发指南", "Programming Guide"],
        "keywords": ["API", "示例代码", "编程指南", "开发指南", "Programming Guide"],
        "negative_keywords": [],
        "file_types": [".pdf", ".md", ".txt"],
        "fallback_rank": 90,
    },
    {
        "id": "tech.general_material",
        "path": ["技术文档", "通用技术资料", "通用技术文档"],
        "label": "通用技术文档",
        "aliases": ["综合技术资料"],
        "keywords": ["技术", "系统", "模块", "接口"],
        "negative_keywords": [],
        "file_types": [".pdf", ".docx", ".md", ".txt"],
        "fallback_rank": 10,
    },
    {
        "id": "books.programming_book",
        "path": ["图书资料", "计算机图书", "编程语言书籍"],
        "label": "编程语言书籍",
        "aliases": ["编程书籍", "Programming Book"],
        "keywords": ["本书", "章节", "示例", "编程", "语言", "教程"],
        "negative_keywords": ["会议纪要"],
        "file_types": [".pdf", ".epub"],
        "fallback_rank": 90,
    },
    {
        "id": "books.software_engineering_book",
        "path": ["图书资料", "计算机图书", "软件工程书籍"],
        "label": "软件工程书籍",
        "aliases": ["重构书籍"],
        "keywords": ["重构", "设计模式", "代码整洁", "软件工程"],
        "negative_keywords": [],
        "file_types": [".pdf", ".epub"],
        "fallback_rank": 90,
    },
    {
        "id": "books.social_science_book",
        "path": ["图书资料", "社科图书", "社科书籍"],
        "label": "社科书籍",
        "aliases": ["社会学书籍", "历史书籍"],
        "keywords": ["社会", "分层", "金融史", "历史", "中国"],
        "negative_keywords": [],
        "file_types": [".pdf", ".epub"],
        "fallback_rank": 90,
    },
    {
        "id": "books.general_book",
        "path": ["图书资料", "综合图书", "综合书籍"],
        "label": "综合书籍",
        "aliases": ["图书资料"],
        "keywords": ["作者", "出版社", "ISBN", "译者"],
        "negative_keywords": [],
        "file_types": [".pdf", ".epub"],
        "fallback_rank": 10,
    },
    {
        "id": "research.industry_report",
        "path": ["研究分析", "行业研究", "行业报告"],
        "label": "行业报告",
        "aliases": ["行业分析", "行业研究报告"],
        "keywords": ["行业", "市场规模", "竞争格局", "趋势"],
        "negative_keywords": [],
        "file_types": [".pdf", ".pptx", ".docx"],
        "fallback_rank": 90,
    },
    {
        "id": "research.analysis_report",
        "path": ["研究分析", "分析研究", "分析报告"],
        "label": "分析报告",
        "aliases": ["研究报告", "分析研究"],
        "keywords": ["分析", "结论", "调研", "数据分析"],
        "negative_keywords": [],
        "file_types": [".pdf", ".docx", ".pptx"],
        "fallback_rank": 90,
    },
    {
        "id": "research.general_report",
        "path": ["研究分析", "综合研究", "综合研究材料"],
        "label": "综合研究材料",
        "aliases": ["综合研究"],
        "keywords": ["研究", "报告", "观察"],
        "negative_keywords": [],
        "file_types": [".pdf", ".docx"],
        "fallback_rank": 10,
    },
    {
        "id": "finance.audit_report",
        "path": ["财务与审计", "审计资料", "审计报告"],
        "label": "审计报告",
        "aliases": ["审计材料"],
        "keywords": ["审计", "底稿", "财务核查"],
        "negative_keywords": [],
        "file_types": [".pdf", ".docx", ".xlsx"],
        "fallback_rank": 90,
    },
    {
        "id": "finance.reimbursement",
        "path": ["财务与审计", "报销付款", "报销单据"],
        "label": "报销单据",
        "aliases": ["报销材料", "付款单"],
        "keywords": ["报销", "付款", "发票", "报销单"],
        "negative_keywords": [],
        "file_types": [".pdf", ".xlsx", ".docx"],
        "fallback_rank": 90,
    },
    {
        "id": "legal.contract",
        "path": ["法务与合规", "合同与协议", "合同协议"],
        "label": "合同协议",
        "aliases": ["合同", "协议"],
        "keywords": ["合同", "协议", "甲方", "乙方", "违约"],
        "negative_keywords": [],
        "file_types": [".pdf", ".docx"],
        "fallback_rank": 90,
    },
    {
        "id": "legal.ip",
        "path": ["法务与合规", "知识产权", "知识产权"],
        "label": "知识产权",
        "aliases": ["IP", "专利"],
        "keywords": ["知识产权", "专利", "商标", "版权"],
        "negative_keywords": [],
        "file_types": [".pdf", ".docx"],
        "fallback_rank": 90,
    },
    {
        "id": "hr.offer_approval",
        "path": ["人力与组织", "招聘管理", "Offer审批"],
        "label": "Offer审批",
        "aliases": ["录用审批", "Offer Approval"],
        "keywords": ["offer", "录用", "入职", "薪资包", "职级"],
        "negative_keywords": [],
        "file_types": [".docx", ".pdf"],
        "fallback_rank": 90,
    },
    {
        "id": "operations.runbook",
        "path": ["运营与服务", "运营体系", "运营手册"],
        "label": "运营手册",
        "aliases": ["运营指南"],
        "keywords": ["运营", "流程", "服务", "手册"],
        "negative_keywords": [],
        "file_types": [".pdf", ".docx"],
        "fallback_rank": 90,
    },
    {
        "id": "product.prd",
        "path": ["产品与项目", "产品设计", "产品需求"],
        "label": "产品需求",
        "aliases": ["PRD", "需求文档"],
        "keywords": ["需求", "用户故事", "产品目标", "交互"],
        "negative_keywords": [],
        "file_types": [".docx", ".md", ".pdf"],
        "fallback_rank": 90,
    },
    {
        "id": "product.project_plan",
        "path": ["产品与项目", "项目管理", "项目方案"],
        "label": "项目方案",
        "aliases": ["项目计划"],
        "keywords": ["项目", "里程碑", "计划", "排期"],
        "negative_keywords": [],
        "file_types": [".docx", ".pptx", ".pdf"],
        "fallback_rank": 90,
    },
    {
        "id": "market.business_plan",
        "path": ["市场与销售", "经营规划", "商业计划"],
        "label": "商业计划",
        "aliases": ["Business Plan"],
        "keywords": ["商业计划", "市场策略", "营收", "客户"],
        "negative_keywords": [],
        "file_types": [".pdf", ".pptx", ".docx"],
        "fallback_rank": 90,
    },
    {
        "id": "data.analysis_report",
        "path": ["数据与智能", "分析研究", "分析报告"],
        "label": "分析报告",
        "aliases": ["数据报告"],
        "keywords": ["数据", "指标", "分析报告", "洞察"],
        "negative_keywords": [],
        "file_types": [".pdf", ".pptx", ".xlsx"],
        "fallback_rank": 90,
    },
    {
        "id": "training.course_material",
        "path": ["培训与知识库", "培训材料", "培训课件"],
        "label": "培训课件",
        "aliases": ["课程材料", "培训资料"],
        "keywords": ["培训", "课件", "课程", "教学"],
        "negative_keywords": [],
        "file_types": [".pptx", ".pdf", ".docx"],
        "fallback_rank": 90,
    },
    {
        "id": "archive.certificate",
        "path": ["档案与证照", "证照档案", "证照材料"],
        "label": "证照材料",
        "aliases": ["资质证照"],
        "keywords": ["证照", "许可证", "执照", "资质"],
        "negative_keywords": [],
        "file_types": [".pdf", ".jpg", ".png"],
        "fallback_rank": 90,
    },
    {
        "id": "general.misc_reference",
        "path": ["通用综合", "综合资料", "综合参考资料"],
        "label": "综合参考资料",
        "aliases": ["综合资料", "综合参考"],
        "keywords": ["资料", "参考", "整理"],
        "negative_keywords": [],
        "file_types": [".pdf", ".docx", ".txt"],
        "fallback_rank": 10,
    },
]


_LABEL_BY_ID = {label["id"]: label for label in LEAF_LABELS}
_DOMAIN_FALLBACKS = {}
for label in LEAF_LABELS:
    if label["fallback_rank"] == 10:
        _DOMAIN_FALLBACKS[label["path"][0]] = label


def get_all_labels() -> list[dict]:
    return [dict(label) for label in LEAF_LABELS]


def get_label_by_id(label_id: str) -> dict | None:
    label = _LABEL_BY_ID.get(str(label_id or ""))
    return dict(label) if label else None


def get_domain_fallback(domain: str) -> dict | None:
    label = _DOMAIN_FALLBACKS.get(str(domain or ""))
    return dict(label) if label else None


def search_by_keyword(text: str, top_k: int = 8, filename_text: str = "") -> list[tuple[dict, float]]:
    haystack = f"{filename_text}\n{text}".lower()
    scored = []
    for label in LEAF_LABELS:
        score = 0.0
        for term in label["aliases"] + label["keywords"]:
            if term.lower() in haystack:
                score += 1.0
        for term in label["negative_keywords"]:
            if term.lower() in haystack:
                score -= 1.5
        if score > 0:
            scored.append((dict(label), score))

    scored.sort(key=lambda item: (-item[1], item[0]["id"]))
    return scored[:top_k]
```

Update `backend/app/domain/taxonomy/__init__.py` to export:

```python
from .unified_document_taxonomy import (
    get_all_labels as get_unified_labels,
    get_domain_fallback,
    get_label_by_id as get_unified_label_by_id,
    search_by_keyword as search_unified_taxonomy,
)
```

- [ ] **Step 4: Re-run the taxonomy catalog tests**

Run: `cd backend && python -m pytest test/test_unified_document_taxonomy.py -v`
Expected: PASS.

- [ ] **Step 5: Commit the unified taxonomy catalog**

```bash
git add backend/app/domain/taxonomy/unified_document_taxonomy.py backend/app/domain/taxonomy/__init__.py backend/test/test_unified_document_taxonomy.py
git commit -m "feat: add unified taxonomy v2 catalog"
```

### Task 3: Refactor TaxonomyClassifier Into Bounded v2 Decision Modules

**Files:**
- Create: `backend/app/services/classification_input_builder.py`
- Create: `backend/app/services/taxonomy_domain_router.py`
- Create: `backend/app/services/taxonomy_candidate_resolver.py`
- Create: `backend/app/services/taxonomy_label_selector.py`
- Create: `backend/app/services/taxonomy_review_policy.py`
- Modify: `backend/app/services/taxonomy_classifier.py`
- Create: `backend/test/test_taxonomy_classifier_v2.py`

- [ ] **Step 1: Write the failing v2 classifier tests**

Create `backend/test/test_taxonomy_classifier_v2.py` with:

```python
import asyncio

from app.services.taxonomy_classifier import TaxonomyClassifier


class _GatewayReturningOperationsManual:
    async def call(self, prompt, task="classify", max_tokens=50, temperature=0.0, use_cache=False):
        assert "tech.operations_manual" in prompt
        return type("Response", (), {"content": "tech.operations_manual"})()


class _GatewayReturningBook:
    async def call(self, prompt, task="classify", max_tokens=50, temperature=0.0, use_cache=False):
        assert "books.software_engineering_book" in prompt
        return type("Response", (), {"content": "books.software_engineering_book"})()


def test_classifier_returns_formal_domain_fallback_for_weak_but_valid_book_signal():
    classifier = TaxonomyClassifier(llm_gateway=_GatewayReturningBook())

    result = asyncio.run(
        classifier.classify(
            document_id="doc-1",
            content="",
            filename="重构：改善既有代码的设计（第2版）.pdf",
            file_type=".pdf",
        )
    )

    assert result["classification_id"] == "books.general_book"
    assert result["classification_label"] == "综合书籍"
    assert result["classification_domain"] == "图书资料"
    assert result["classification_issue_code"] is None
    assert result["taxonomy_version"] == "taxonomy_v2"


def test_classifier_selects_specific_leaf_for_clear_technical_manual():
    classifier = TaxonomyClassifier(llm_gateway=_GatewayReturningOperationsManual())

    result = asyncio.run(
        classifier.classify(
            document_id="doc-2",
            content="值班流程、故障应急、巡检规范和变更窗口说明。",
            filename="操作系统运维手册.pdf",
            file_type=".pdf",
        )
    )

    assert result["classification_id"] == "tech.operations_manual"
    assert result["classification_path"] == ["技术文档", "运维体系", "运维手册"]
    assert result["classification_domain"] == "技术文档"
    assert result["classification_review_status"] == "accepted"
    assert result["taxonomy_version"] == "taxonomy_v2"


def test_classifier_keeps_raw_no_match_for_empty_content():
    classifier = TaxonomyClassifier(llm_gateway=_GatewayReturningOperationsManual())

    result = asyncio.run(
        classifier.classify(
            document_id="doc-3",
            content="   \n  ",
            filename="empty.pdf",
            file_type=".pdf",
        )
    )

    assert result["classification_id"] is None
    assert result["classification_issue_code"] == "no_match"
    assert result["classification_review_status"] == "needs_review"
```

- [ ] **Step 2: Run the v2 classifier tests and verify they fail**

Run: `cd backend && python -m pytest test/test_taxonomy_classifier_v2.py -v`
Expected: FAIL because the helper modules and v2 output fields do not exist yet.

- [ ] **Step 3: Implement the modular classifier flow**

Create `backend/app/services/classification_input_builder.py` with:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ClassificationInput:
    document_id: str
    content: str
    filename: str
    file_type: str
    title_text: str
    normalized_text: str
    is_blank: bool


def build_classification_input(document_id: str, content: str, filename: str, file_type: str) -> ClassificationInput:
    normalized_text = str(content or "").strip()
    title_text = str(filename or "").rsplit(".", 1)[0].strip()
    meaningful_title = title_text.lower() not in {"", "empty", "blank", "untitled", "无标题"}
    return ClassificationInput(
        document_id=document_id,
        content=str(content or ""),
        filename=str(filename or ""),
        file_type=str(file_type or ""),
        title_text=title_text,
        normalized_text=normalized_text[:4000],
        is_blank=not bool(normalized_text) and not meaningful_title,
    )
```

Create `backend/app/services/taxonomy_domain_router.py` with:

```python
from app.domain.taxonomy.unified_document_taxonomy import get_all_labels


def route_domains(classification_input) -> list[str]:
    haystack = f"{classification_input.filename}\n{classification_input.normalized_text}".lower()
    if any(token in haystack for token in ["本书", "作者", "出版社", "isbn"]):
        return ["图书资料", "通用综合"]
    if any(token in haystack for token in ["运维", "架构", "api", "编程", "系统设计"]):
        return ["技术文档", "图书资料"]
    if any(token in haystack for token in ["汇报", "纪要", "制度", "方案", "审批"]):
        return ["办公文档", "产品与项目"]
    return ["通用综合", "办公文档", "技术文档"]
```

Create `backend/app/services/taxonomy_candidate_resolver.py` with:

```python
from app.domain.taxonomy.unified_document_taxonomy import get_all_labels, search_by_keyword


def resolve_candidates(classification_input, domains: list[str]) -> list[tuple[dict, float]]:
    recalled = search_by_keyword(
        classification_input.normalized_text,
        filename_text=classification_input.filename,
        top_k=12,
    )
    domain_set = set(domains)
    filtered = [
        (label, score)
        for label, score in recalled
        if label["path"][0] in domain_set
    ]
    return filtered
```

Create `backend/app/services/taxonomy_label_selector.py` with:

```python
async def select_label_id(llm_gateway, classification_input, candidates: list[dict]) -> tuple[str | None, float]:
    if not candidates:
        return None, 0.0
    labels_text = "\n".join(
        f"- {item['id']} | {' > '.join(item['path'])} | {item['label']}"
        for item in candidates
    )
    prompt = (
        "你是文档分类助手。\n"
        "请只从候选分类中选择一个最合适的 leaf id。\n\n"
        f"候选分类：\n{labels_text}\n\n"
        f"文件名：{classification_input.filename}\n"
        f"内容：{classification_input.normalized_text[:2000]}\n\n"
        "直接返回 leaf id："
    )
    try:
        response = await llm_gateway.call(prompt, task="classify", max_tokens=30, temperature=0.0, use_cache=False)
    except Exception:
        return None, 0.0
    selected_id = str(getattr(response, "content", "") or "").strip()
    return (selected_id if selected_id else None, 0.75 if selected_id else 0.0)
```

Create `backend/app/services/taxonomy_review_policy.py` with:

```python
from app.domain.taxonomy.unified_document_taxonomy import get_domain_fallback


def build_review_result():
    return {
        "classification_id": None,
        "classification_leaf_id": None,
        "classification_label": None,
        "classification_path": [],
        "classification_domain": None,
        "classification_score": 0.0,
        "classification_confidence": 0.0,
        "classification_source": "fallback",
        "classification_candidates": [],
        "classification_review_status": "needs_review",
        "classification_issue_code": "no_match",
        "taxonomy_version": "taxonomy_v2",
    }


def finalize_result(label: dict | None, *, domain: str | None, confidence: float, candidates: list[str], accept_threshold: float = 0.55):
    if label is not None and confidence >= accept_threshold:
        return {
            "classification_id": label["id"],
            "classification_leaf_id": label["id"],
            "classification_label": label["label"],
            "classification_path": label["path"],
            "classification_domain": label["path"][0],
            "classification_score": confidence,
            "classification_confidence": confidence,
            "classification_source": "llm",
            "classification_candidates": candidates,
            "classification_review_status": "accepted",
            "classification_issue_code": None,
            "taxonomy_version": "taxonomy_v2",
        }

    fallback = get_domain_fallback(domain or "")
    if fallback:
        return {
            "classification_id": fallback["id"],
            "classification_leaf_id": fallback["id"],
            "classification_label": fallback["label"],
            "classification_path": fallback["path"],
            "classification_domain": fallback["path"][0],
            "classification_score": max(confidence, 0.35),
            "classification_confidence": max(confidence, 0.35),
            "classification_source": "domain_fallback",
            "classification_candidates": candidates,
            "classification_review_status": "accepted",
            "classification_issue_code": None,
            "taxonomy_version": "taxonomy_v2",
        }

    return build_review_result()
```

Update `backend/app/services/taxonomy_classifier.py` so `classify()` orchestrates the helpers and mirrors `classification_confidence` into `classification_score` for compatibility:

```python
classification_input = build_classification_input(document_id, content, filename, file_type)
if classification_input.is_blank:
    return build_review_result()

domains = route_domains(classification_input)
candidates = resolve_candidates(classification_input, domains)
candidate_ids = [label["id"] for label, _score in candidates[:5]]
selected_id, llm_confidence = await select_label_id(
    self.llm_gateway,
    classification_input,
    [label for label, _score in candidates[:5]],
)
selected_label = get_label_by_id(selected_id) if selected_id else None
primary_domain = candidates[0][0]["path"][0] if candidates else (domains[0] if domains else None)
return finalize_result(
    selected_label,
    domain=primary_domain,
    confidence=float(llm_confidence or 0.0),
    candidates=candidate_ids,
)
```

- [ ] **Step 4: Re-run the v2 classifier tests**

Run: `cd backend && python -m pytest test/test_taxonomy_classifier_v2.py -v`
Expected: PASS.

- [ ] **Step 5: Commit the classifier refactor**

```bash
git add backend/app/services/classification_input_builder.py backend/app/services/taxonomy_domain_router.py backend/app/services/taxonomy_candidate_resolver.py backend/app/services/taxonomy_label_selector.py backend/app/services/taxonomy_review_policy.py backend/app/services/taxonomy_classifier.py backend/test/test_taxonomy_classifier_v2.py
git commit -m "refactor: split taxonomy v2 classifier flow"
```

### Task 4: Wire Classification Service, Backfill, And Frontend Compatibility Around v2

**Files:**
- Create: `backend/app/services/taxonomy_compatibility.py`
- Create: `backend/test/test_classification_service_v2.py`
- Modify: `backend/app/services/classification_service.py`
- Modify: `backend/app/schemas/classification.py`
- Modify: `backend/migrations/backfill_taxonomy.py`
- Modify: `frontend/docagent-frontend/src/components/FileList.vue`
- Modify: `frontend/docagent-frontend/src/components/__tests__/FileList.spec.js`

- [ ] **Step 1: Write the failing service and frontend compatibility tests**

Create `backend/test/test_classification_service_v2.py` with:

```python
import asyncio

import app.services.classification_service as classification_service_module
from app.services.classification_service import ClassificationService


def test_classification_service_persists_v2_assignment_fields(monkeypatch):
    monkeypatch.setattr(
        classification_service_module,
        "get_document_info",
        lambda document_id: {"id": document_id, "filename": "guide.pdf", "file_type": ".pdf"},
    )
    monkeypatch.setattr(
        classification_service_module,
        "get_document_content_record",
        lambda document_id: {"full_content": "值班流程、故障处理、巡检和变更窗口"},
    )
    monkeypatch.setattr(classification_service_module, "is_error_document", lambda *args, **kwargs: False)

    updates = []
    monkeypatch.setattr(
        classification_service_module,
        "update_document_info",
        lambda document_id, updated_info: updates.append(updated_info) or True,
    )

    class FakeTaxonomyClassifier:
        async def classify(self, document_id, content, filename="", file_type=""):
            return {
                "classification_id": "tech.operations_manual",
                "classification_leaf_id": "tech.operations_manual",
                "classification_label": "运维手册",
                "classification_path": ["技术文档", "运维体系", "运维手册"],
                "classification_domain": "技术文档",
                "classification_score": 0.88,
                "classification_confidence": 0.88,
                "classification_source": "llm",
                "classification_candidates": ["tech.operations_manual"],
                "classification_review_status": "accepted",
                "classification_issue_code": None,
                "taxonomy_version": "taxonomy_v2",
            }

    monkeypatch.setattr(classification_service_module, "TaxonomyClassifier", FakeTaxonomyClassifier)

    result = ClassificationService().classify("doc-1")

    assert result["topic_id"] == "tech.operations_manual"
    assert result["topic_path"] == ["技术文档", "运维体系", "运维手册"]
    assert updates[0]["taxonomy_version"] == "taxonomy_v2"
    assert updates[0]["classification_leaf_id"] == "tech.operations_manual"
```

Append to `frontend/docagent-frontend/src/components/__tests__/FileList.spec.js`:

```javascript
it('shows formal fallback paths and keeps raw no_match reserved for abnormal documents', () => {
  const wrapper = mountFileList()

  expect(
    wrapper.vm.getClassificationText({
      classification_path: ['图书资料', '综合图书', '综合书籍'],
      classification_source: 'domain_fallback',
      classification_issue_code: null
    })
  ).toBe('图书资料 > 综合图书 > 综合书籍')

  expect(wrapper.vm.getClassificationSourceMeta('domain_fallback')).toEqual({ label: '兜底分类', tone: 'fallback' })
  expect(wrapper.vm.getClassificationText({ classification_issue_code: 'no_match' })).toBe('未分类')
})
```

- [ ] **Step 2: Run the compatibility tests and verify they fail**

Run: `cd backend && python -m pytest test/test_classification_service_v2.py -v`
Expected: FAIL because `ClassificationService` does not persist v2-only fields yet.

Run: `cd frontend/docagent-frontend && npm run test -- src/components/__tests__/FileList.spec.js`
Expected: FAIL because `domain_fallback` source metadata is not mapped yet.

- [ ] **Step 3: Implement compatibility mapping, service persistence, and frontend badge support**

Create `backend/app/services/taxonomy_compatibility.py` with:

```python
LEGACY_LABEL_TO_V2 = {
    "Offer审批": {
        "classification_leaf_id": "hr.offer_approval",
        "classification_label": "Offer审批",
        "classification_path": ["人力与组织", "招聘管理", "Offer审批"],
        "classification_domain": "人力与组织",
        "taxonomy_version": "taxonomy_v2",
    },
    "运维手册": {
        "classification_leaf_id": "tech.operations_manual",
        "classification_label": "运维手册",
        "classification_path": ["技术文档", "运维体系", "运维手册"],
        "classification_domain": "技术文档",
        "taxonomy_version": "taxonomy_v2",
    },
}


def map_legacy_assignment(label: str | None) -> dict | None:
    payload = LEGACY_LABEL_TO_V2.get(str(label or "").strip())
    return dict(payload) if payload else None


def normalize_assignment(result: dict) -> dict:
    normalized = dict(result)
    normalized["classification_id"] = result.get("classification_leaf_id") or result.get("classification_id")
    normalized["classification_score"] = float(result.get("classification_confidence") or result.get("classification_score") or 0.0)
    normalized["taxonomy_version"] = result.get("taxonomy_version") or "taxonomy_v1"
    return normalized
```

Update `_save_taxonomy_result()` in `backend/app/services/classification_service.py` so it persists the v2 keys:

```python
normalized = normalize_assignment(result)
update_document_info(
    document_id,
    {
        "classification_result": normalized.get("classification_label"),
        "classification_id": normalized.get("classification_id"),
        "classification_leaf_id": normalized.get("classification_leaf_id"),
        "classification_path": normalized.get("classification_path") or [],
        "classification_domain": normalized.get("classification_domain"),
        "classification_score": normalized.get("classification_score"),
        "classification_confidence": normalized.get("classification_confidence"),
        "classification_source": normalized.get("classification_source"),
        "classification_candidates": normalized.get("classification_candidates") or [],
        "classification_review_status": normalized.get("classification_review_status"),
        "classification_issue_code": normalized.get("classification_issue_code"),
        "taxonomy_version": normalized.get("taxonomy_version"),
    },
)
```

Update `backend/app/schemas/classification.py` so `ClassificationResponse` gains optional compatibility fields:

```python
classification_leaf_id: Optional[str] = None
classification_domain: Optional[str] = None
taxonomy_version: str = "taxonomy_v1"
```

Update `backend/migrations/backfill_taxonomy.py` to map legacy rows before keyword fallback:

```python
from app.services.taxonomy_compatibility import map_legacy_assignment

legacy = map_legacy_assignment(row["classification_result"])
if legacy:
    connection.execute(
        """
        UPDATE documents
        SET classification_id = ?,
            classification_leaf_id = ?,
            classification_path = ?,
            classification_domain = ?,
            taxonomy_version = ?
        WHERE id = ?
        """,
        (
            legacy["classification_leaf_id"],
            legacy["classification_leaf_id"],
            json.dumps(legacy["classification_path"], ensure_ascii=False),
            legacy["classification_domain"],
            legacy["taxonomy_version"],
            row["id"],
        ),
    )
    updated += 1
    continue
```

Update `frontend/docagent-frontend/src/components/FileList.vue` in `getClassificationSourceMeta()`:

```javascript
const dictionary = {
  llm: { label: 'AI', tone: 'ai' },
  llm_forced: { label: 'AI', tone: 'ai' },
  keyword: { label: '关键词', tone: 'keyword' },
  keyword_forced: { label: '模板分类', tone: 'keyword' },
  fallback: { label: '待确认', tone: 'fallback' },
  domain_fallback: { label: '兜底分类', tone: 'fallback' },
  pending_local_content: { label: '待本地索引', tone: 'pending' }
}
```

- [ ] **Step 4: Re-run the compatibility tests**

Run: `cd backend && python -m pytest test/test_classification_service_v2.py test/test_taxonomy_migrations.py -v`
Expected: PASS.

Run: `cd frontend/docagent-frontend && npm run test -- src/components/__tests__/FileList.spec.js`
Expected: PASS.

- [ ] **Step 5: Commit the compatibility wiring**

```bash
git add backend/app/services/taxonomy_compatibility.py backend/app/services/classification_service.py backend/app/schemas/classification.py backend/migrations/backfill_taxonomy.py backend/test/test_classification_service_v2.py frontend/docagent-frontend/src/components/FileList.vue frontend/docagent-frontend/src/components/__tests__/FileList.spec.js
git commit -m "feat: wire taxonomy v2 compatibility across service and UI"
```

## Verification

- [ ] Run: `cd backend && python -m pytest test/test_taxonomy_v2_storage.py test/test_unified_document_taxonomy.py test/test_taxonomy_classifier_v2.py test/test_classification_service_v2.py test/test_taxonomy_migrations.py -v`
- [ ] Run: `cd backend && python -m pytest test/test_taxonomy_classifier.py test/test_classification_tables.py -v`
- [ ] Run: `cd frontend/docagent-frontend && npm run test -- src/components/__tests__/FileList.spec.js`
- [ ] Manually confirm:

```text
1. New documents persist taxonomy_version, classification_leaf_id, classification_domain, and classification_confidence.
2. Weak but valid book-like or tech-like documents land on formal fallback labels instead of raw no_match.
3. Blank or unreadable content still produces no_match and 待复核.
4. /documents keeps rendering classification_path normally and shows the new domain_fallback badge.
```
