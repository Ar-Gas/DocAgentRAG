# Taxonomy V3 Hierarchical Classification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `taxonomy_v3`, a broad fixed three-level classifier that classifies normal documents into real leaf categories and stops new documents from landing in `未分类 / 待复核 / no_match`.

**Architecture:** Add a standalone `taxonomy_v3` catalog and a two-stage LLM classifier. Stage 1 selects the top-level domain, stage 2 selects a legal leaf path inside that domain, and failures fall back to that domain's concrete fallback leaf. Keep existing document classification storage fields, add batch reclassification, and update `/documents` display so classification and ingest errors are visually separate.

**Tech Stack:** Python 3.12, FastAPI, sqlite metadata store, pytest, Vue 3, Vitest

---

## File Structure

- Create: `backend/app/domain/taxonomy/universal_taxonomy_v3.py`
  Responsibility: fixed `taxonomy_v3` catalog, path lookup, fallback lookup, domain grouping, and simple filename/content heuristics.
- Modify: `backend/app/domain/taxonomy/__init__.py`
  Responsibility: export the v3 catalog helpers.
- Create: `backend/app/services/taxonomy_v3_llm_protocol.py`
  Responsibility: parse and validate fixed LLM output lines and slash-separated paths.
- Create: `backend/app/services/taxonomy_v3_classifier.py`
  Responsibility: two-stage LLM classification and deterministic fallback result serialization.
- Modify: `backend/app/services/taxonomy_classifier.py`
  Responsibility: delegate the active classifier to `TaxonomyV3Classifier` while preserving the existing public class used by `ClassificationService`.
- Modify: `backend/app/services/classification_service.py`
  Responsibility: persist `taxonomy_v3` assignments, support batch reclassification, and avoid normal `no_match` writes.
- Modify: `backend/app/schemas/classification.py`
  Responsibility: add request models for batch reclassification filters.
- Modify: `backend/api/classification.py`
  Responsibility: add explicit batch reclassification API.
- Modify: `backend/api/document.py`
  Responsibility: expose v3 classification metadata to `/documents`.
- Modify: `frontend/docagent-frontend/src/api/index.js`
  Responsibility: add client call for batch reclassification.
- Modify: `frontend/docagent-frontend/src/components/FileList.vue`
  Responsibility: display v3 paths and fallback badges, and stop mixing ingest/local-index errors into classification text.
- Create: `backend/test/test_taxonomy_v3_catalog.py`
- Create: `backend/test/test_taxonomy_v3_llm_protocol.py`
- Create: `backend/test/test_taxonomy_v3_classifier.py`
- Modify: `backend/test/test_taxonomy_classifier.py`
- Modify: `backend/test/test_classification_service_v2.py`
- Create: `backend/test/test_batch_reclassification.py`
- Modify: `backend/test/test_document_reader_api.py`
- Modify: `frontend/docagent-frontend/src/components/__tests__/FileList.spec.js`

## Catalog Appendix

Implement the v3 catalog with the following exact domains, second-level groups, and leaves. Each group listed here becomes a second-level path component. Each leaf listed here becomes a third-level path component.

### 办公文档

- `综合办公`: `通用办公材料`, `通知公告`, `申请审批`, `工作汇报`, `办公模板`
- `会议纪要`: `会议纪要`, `会议议程`, `会议材料`, `会议决议`, `行动项跟踪`
- `制度流程`: `管理制度`, `流程规范`, `操作规程`, `内控流程`, `制度汇编`
- `行政后勤`: `行政通知`, `资产登记`, `办公用品`, `后勤安排`, `用印申请`

### 财务税务

- `综合财务`: `通用财务材料`, `财务说明`, `财务制度`, `财务台账`, `财务附件`
- `出纳结算`: `出纳管理`, `银行流水`, `现金日记账`, `资金调拨`, `账户管理`
- `报销付款`: `费用报销`, `付款审批`, `差旅报销`, `借款申请`, `付款凭证`
- `账务报表`: `财务月报`, `资产负债表`, `利润表`, `现金流量表`, `审计报告`
- `预算成本`: `预算申请`, `成本分析`, `费用预算`, `预算执行`, `成本台账`
- `税务管理`: `税务申报`, `发票台账`, `纳税资料`, `税务筹划`, `税务审查`

### 人力组织

- `综合人事`: `通用人事材料`, `人事通知`, `组织架构`, `员工手册`, `人事台账`
- `招聘录用`: `招聘需求`, `Offer审批`, `面试记录`, `岗位说明`, `录用材料`
- `员工关系`: `入职材料`, `离职办理`, `劳动合同`, `员工证明`, `关系处理`
- `绩效薪酬`: `绩效考核`, `薪酬方案`, `奖金方案`, `调薪审批`, `考勤记录`
- `培训发展`: `培训计划`, `课程材料`, `学习地图`, `培训记录`, `人才盘点`

### 法务合规

- `综合法务`: `通用法务材料`, `法务说明`, `合规材料`, `法律资料`, `法务台账`
- `合同协议`: `标准合同`, `销售合同`, `采购合同`, `合作协议`, `补充协议`
- `审查意见`: `法务审查`, `法律意见`, `风险提示`, `合同审查`, `争议处理`
- `知识产权`: `知识产权`, `专利资料`, `商标资料`, `著作权资料`, `授权许可`
- `授权资质`: `授权文件`, `资质证明`, `委托书`, `证照资料`, `用印授权`
- `隐私合规`: `隐私条款`, `数据合规`, `安全承诺`, `监管要求`, `合规制度`

### 产品项目

- `综合项目`: `通用项目材料`, `项目说明`, `项目附件`, `项目资料`, `综合项目文档`
- `需求规划`: `需求文档`, `版本规划`, `产品路线图`, `需求清单`, `功能说明`
- `项目管理`: `项目计划`, `项目周报`, `项目复盘`, `风险清单`, `里程碑计划`
- `交付验收`: `验收清单`, `交付文档`, `验收报告`, `上线计划`, `发布说明`
- `用户研究`: `用户调研`, `访谈记录`, `问卷分析`, `用户画像`, `可用性测试`

### 研发技术

- `综合技术`: `通用技术文档`, `技术资料`, `技术说明`, `研发资料`, `技术附件`
- `架构设计`: `架构设计`, `系统设计`, `模块设计`, `技术选型`, `方案设计`
- `接口文档`: `接口文档`, `API文档`, `协议说明`, `参数说明`, `集成文档`
- `开发规范`: `开发手册`, `编码规范`, `工程规范`, `代码说明`, `开发指南`
- `测试质量`: `测试用例`, `测试计划`, `缺陷报告`, `质量报告`, `验收测试`
- `技术方案`: `技术方案`, `实现方案`, `迁移方案`, `性能优化`, `技术调研`

### 运维安全

- `综合运维`: `通用运维材料`, `运维资料`, `运维说明`, `安全资料`, `运维附件`
- `运维体系`: `运维手册`, `运行手册`, `部署手册`, `操作手册`, `值班手册`
- `监控告警`: `巡检记录`, `监控报表`, `告警规则`, `容量报告`, `健康检查`
- `故障应急`: `故障复盘`, `应急预案`, `应急演练`, `事故报告`, `恢复方案`
- `安全治理`: `安全规范`, `安全策略`, `漏洞报告`, `权限管理`, `安全基线`
- `变更资产`: `变更记录`, `变更申请`, `资产台账`, `配置清单`, `发布变更`

### 数据分析

- `综合分析`: `通用分析材料`, `分析资料`, `数据说明`, `分析附件`, `数据材料`
- `经营分析`: `经营复盘`, `经营月报`, `经营看板`, `业务分析`, `增长分析`
- `专题分析`: `分析报告`, `专题报告`, `趋势分析`, `归因分析`, `实验分析`
- `报表看板`: `数据周报`, `报表说明`, `看板说明`, `指标报表`, `统计报表`
- `数据治理`: `指标口径`, `数据字典`, `建模方案`, `数据质量`, `元数据说明`

### 销售商务

- `综合销售`: `通用销售材料`, `销售资料`, `商务材料`, `销售附件`, `商务说明`
- `售前方案`: `销售方案`, `解决方案`, `售前材料`, `客户方案`, `方案报价`
- `报价投标`: `商务报价`, `投标应答`, `标书材料`, `询价回复`, `报价清单`
- `客户合同`: `销售合同`, `客户协议`, `续约材料`, `回款资料`, `客户订单`
- `客户跟进`: `拜访记录`, `客户纪要`, `跟进记录`, `商机记录`, `客户需求`

### 市场品牌

- `综合市场`: `通用市场材料`, `市场资料`, `品牌材料`, `市场附件`, `营销说明`
- `市场策划`: `市场方案`, `营销计划`, `传播方案`, `增长方案`, `渠道方案`
- `活动运营`: `活动策划`, `活动执行`, `活动复盘`, `会务材料`, `物料清单`
- `品牌管理`: `品牌规范`, `视觉规范`, `品牌手册`, `商标素材`, `品牌资产`
- `内容营销`: `推广素材`, `内容计划`, `文案素材`, `媒体稿件`, `投放素材`
- `竞品研究`: `竞品分析`, `竞品资料`, `市场调研`, `对标分析`, `行业观察`

### 客户服务

- `综合服务`: `通用服务材料`, `服务资料`, `客服材料`, `服务附件`, `客户说明`
- `服务体系`: `服务手册`, `SLA协议`, `服务流程`, `客服话术`, `支持指南`
- `工单运营`: `工单周报`, `工单月报`, `工单分析`, `问题清单`, `处理记录`
- `客户反馈`: `客户反馈`, `满意度调查`, `用户建议`, `体验反馈`, `回访记录`
- `投诉处理`: `投诉记录`, `投诉处理`, `升级记录`, `客诉分析`, `赔付说明`

### 图书资料

- `综合图书`: `综合书籍`, `通用图书资料`, `图书目录`, `阅读资料`, `参考书籍`
- `计算机图书`: `编程语言书籍`, `计算机基础教材`, `软件工程书籍`, `数据库书籍`, `人工智能书籍`, `网络安全书籍`
- `经济金融图书`: `金融历史书籍`, `经济学书籍`, `投资理财书籍`, `会计财务书籍`, `商业管理书籍`
- `社科图书`: `社会学书籍`, `历史文化书籍`, `政治法律书籍`, `心理学书籍`, `教育学书籍`
- `科技产业图书`: `互联网产业书籍`, `科技史书籍`, `产业分析书籍`, `企业传记书籍`, `创新创业书籍`

### 研究分析

- `综合研究`: `通用研究材料`, `研究资料`, `研究综述`, `参考资料`, `研究附件`
- `行业研究`: `行业报告`, `市场规模报告`, `竞争格局报告`, `趋势报告`, `产业链报告`
- `学术论文`: `学术论文`, `会议论文`, `期刊论文`, `学位论文`, `实验论文`
- `政策研究`: `政策解读`, `政策汇编`, `监管分析`, `法规研究`, `政策建议`
- `咨询报告`: `咨询报告`, `调研报告`, `诊断报告`, `战略报告`, `可研报告`

### Task 1: Add `taxonomy_v3` Catalog Contract

**Files:**
- Create: `backend/app/domain/taxonomy/universal_taxonomy_v3.py`
- Modify: `backend/app/domain/taxonomy/__init__.py`
- Create: `backend/test/test_taxonomy_v3_catalog.py`
- Test: `backend/test/test_taxonomy_v3_catalog.py`

- [ ] **Step 1: Write failing catalog tests**

Create `backend/test/test_taxonomy_v3_catalog.py`:

```python
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.domain.taxonomy.universal_taxonomy_v3 import (  # noqa: E402
    TAXONOMY_VERSION,
    get_all_labels,
    get_domain_fallback,
    get_domain_options,
    get_label_by_path,
    get_labels_by_domain,
    infer_domain_from_filename,
)


def test_taxonomy_v3_catalog_shape_and_size():
    labels = get_all_labels()
    paths = [tuple(label["path"]) for label in labels]
    ids = [label["id"] for label in labels]

    assert TAXONOMY_VERSION == "taxonomy_v3"
    assert len(labels) >= 220
    assert len(paths) == len(set(paths))
    assert len(ids) == len(set(ids))
    assert all(len(label["path"]) == 3 for label in labels)


def test_taxonomy_v3_domains_have_single_fallback_leaf():
    domains = get_domain_options()

    assert "办公文档" in domains
    assert "图书资料" in domains
    assert "研究分析" in domains

    for domain in domains:
        fallback = get_domain_fallback(domain)
        domain_labels = get_labels_by_domain(domain)
        fallback_labels = [label for label in domain_labels if label.get("fallback")]

        assert fallback["path"][0] == domain
        assert len(fallback["path"]) == 3
        assert len(fallback_labels) == 1
        assert fallback_labels[0]["id"] == fallback["id"]


def test_taxonomy_v3_can_lookup_book_and_office_paths():
    assert get_label_by_path(["图书资料", "计算机图书", "编程语言书籍"])["id"] == "books.computer.programming_language"
    assert get_label_by_path(["办公文档", "综合办公", "通用办公材料"])["fallback"] is True
    assert get_label_by_path(["研发技术", "综合技术", "通用技术文档"])["fallback"] is True


def test_taxonomy_v3_filename_domain_heuristics_prefer_books_for_book_titles():
    assert infer_domain_from_filename("Rust编程：入门、实战与进阶.pdf", ".pdf") == "图书资料"
    assert infer_domain_from_filename("操作系统导论.pdf", ".pdf") == "图书资料"
    assert infer_domain_from_filename("付款审批单.xlsx", ".xlsx") == "财务税务"
```

- [ ] **Step 2: Run the catalog tests and verify failure**

Run: `cd backend && .venv/bin/python -m pytest test/test_taxonomy_v3_catalog.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'app.domain.taxonomy.universal_taxonomy_v3'`.

- [ ] **Step 3: Implement the catalog module**

Create `backend/app/domain/taxonomy/universal_taxonomy_v3.py` with this structure. Populate `CATALOG` from the Catalog Appendix above.

```python
from __future__ import annotations

import os
from typing import Any

TAXONOMY_VERSION = "taxonomy_v3"


def _leaf(
    leaf_id: str,
    domain: str,
    group: str,
    label: str,
    *,
    aliases: list[str] | None = None,
    keywords: list[str] | None = None,
    description: str = "",
    fallback: bool = False,
) -> dict[str, Any]:
    return {
        "id": leaf_id,
        "path": [domain, group, label],
        "label": label,
        "description": description or f"{domain}/{group}/{label}",
        "aliases": aliases or [],
        "keywords": keywords or [],
        "fallback": fallback,
        "taxonomy_version": TAXONOMY_VERSION,
    }


CATALOG: list[dict[str, Any]] = [
    _leaf("office.general.general_material", "办公文档", "综合办公", "通用办公材料", fallback=True, keywords=["办公", "材料", "附件", "模板"]),
    _leaf("office.general.notice", "办公文档", "综合办公", "通知公告", keywords=["通知", "公告", "发布"]),
    _leaf("office.general.approval", "办公文档", "综合办公", "申请审批", keywords=["申请", "审批", "流程"]),
    _leaf("office.general.report", "办公文档", "综合办公", "工作汇报", keywords=["汇报", "总结", "复盘"]),
    _leaf("office.general.template", "办公文档", "综合办公", "办公模板", keywords=["模板", "表单", "样例"]),
    _leaf("books.computer.programming_language", "图书资料", "计算机图书", "编程语言书籍", keywords=["Rust", "C++", "Python", "编程", "代码", "教程"]),
    _leaf("books.computer.computer_fundamentals", "图书资料", "计算机图书", "计算机基础教材", keywords=["操作系统", "计算机组成", "算法", "网络", "教材"]),
    _leaf("books.computer.software_engineering", "图书资料", "计算机图书", "软件工程书籍", keywords=["重构", "设计模式", "代码质量", "软件工程"]),
    _leaf("books.technology.internet_industry", "图书资料", "科技产业图书", "互联网产业书籍", keywords=["互联网", "科技公司", "产业", "浪潮之巅"]),
    _leaf("books.finance.financial_history", "图书资料", "经济金融图书", "金融历史书籍", keywords=["金融史", "货币", "银行", "经济史"]),
    _leaf("books.social.social_science", "图书资料", "社科图书", "社会学书籍", keywords=["社会", "分层", "社会学", "阶层"]),
]


_BY_ID = {label["id"]: label for label in CATALOG}
_BY_PATH = {tuple(label["path"]): label for label in CATALOG}
_DOMAINS = list(dict.fromkeys(label["path"][0] for label in CATALOG))


def _copy_label(label: dict[str, Any] | None) -> dict[str, Any] | None:
    if label is None:
        return None
    copied = dict(label)
    copied["path"] = list(label.get("path") or [])
    copied["aliases"] = list(label.get("aliases") or [])
    copied["keywords"] = list(label.get("keywords") or [])
    return copied


def get_all_labels() -> list[dict[str, Any]]:
    return [_copy_label(label) for label in CATALOG]


def get_domain_options() -> list[str]:
    return list(_DOMAINS)


def get_label_by_id(label_id: str) -> dict[str, Any] | None:
    return _copy_label(_BY_ID.get(str(label_id or "")))


def get_label_by_path(path: list[str] | tuple[str, str, str] | str) -> dict[str, Any] | None:
    if isinstance(path, str):
        parts = [part.strip() for part in path.replace(">", "/").split("/") if part.strip()]
    else:
        parts = [str(part or "").strip() for part in path]
    if len(parts) != 3:
        return None
    return _copy_label(_BY_PATH.get(tuple(parts)))


def get_labels_by_domain(domain: str) -> list[dict[str, Any]]:
    normalized = str(domain or "").strip()
    return [_copy_label(label) for label in CATALOG if label["path"][0] == normalized]


def get_domain_fallback(domain: str) -> dict[str, Any]:
    normalized = str(domain or "").strip()
    for label in CATALOG:
        if label["path"][0] == normalized and label.get("fallback"):
            return _copy_label(label)
    return _copy_label(next(label for label in CATALOG if label.get("fallback")))


def format_path(label: dict[str, Any]) -> str:
    return "/".join(label.get("path") or [])


def infer_domain_from_filename(filename: str, file_type: str = "") -> str:
    text = f"{filename or ''} {file_type or os.path.splitext(str(filename or ''))[1]}".lower()
    if any(word.lower() in text for word in ["rust", "c++", "编程", "教程", "导论", "z-library", "书籍", "pdf"]):
        if any(word.lower() in text for word in ["审批", "报销", "合同", "会议"]):
            return "办公文档"
        return "图书资料"
    if any(word in text for word in ["付款", "报销", "发票", "出纳", "预算", "财务"]):
        return "财务税务"
    if any(word in text for word in ["合同", "协议", "法务", "合规"]):
        return "法务合规"
    if any(word in text for word in ["研究", "报告", "论文", "政策"]):
        return "研究分析"
    return "办公文档"
```

The snippet shows the required module structure plus the highest-risk regression leaves. The final `CATALOG` must include every leaf in the Catalog Appendix before running tests. Use stable IDs in the format `<english-domain>.<english-group>.<english-leaf>`. Use `fallback=True` only for the 13 domain fallback leaves listed in the spec.

- [ ] **Step 4: Export the module**

Modify `backend/app/domain/taxonomy/__init__.py`:

```python
from app.domain.taxonomy.universal_taxonomy_v3 import (  # noqa: F401
    TAXONOMY_VERSION,
    format_path,
    get_all_labels,
    get_domain_fallback,
    get_domain_options,
    get_label_by_id,
    get_label_by_path,
    get_labels_by_domain,
    infer_domain_from_filename,
)
```

- [ ] **Step 5: Run catalog tests and verify pass**

Run: `cd backend && .venv/bin/python -m pytest test/test_taxonomy_v3_catalog.py -q`

Expected: PASS.

- [ ] **Step 6: Commit the catalog**

```bash
git add backend/app/domain/taxonomy/universal_taxonomy_v3.py backend/app/domain/taxonomy/__init__.py backend/test/test_taxonomy_v3_catalog.py
git commit -m "feat: add taxonomy v3 catalog"
```

### Task 2: Add Fixed LLM Output Protocol Parser

**Files:**
- Create: `backend/app/services/taxonomy_v3_llm_protocol.py`
- Create: `backend/test/test_taxonomy_v3_llm_protocol.py`
- Test: `backend/test/test_taxonomy_v3_llm_protocol.py`

- [ ] **Step 1: Write failing parser tests**

Create `backend/test/test_taxonomy_v3_llm_protocol.py`:

```python
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.taxonomy_v3_llm_protocol import (  # noqa: E402
    parse_classification_output,
)


def test_parse_line_protocol_with_valid_taxonomy_path():
    parsed = parse_classification_output(
        """
        一级域: 图书资料
        二级类: 计算机图书
        三级类: 编程语言书籍
        是否兜底: 否
        置信度: 0.91
        依据: 文件名包含 Rust 编程，正文包含示例代码。
        """
    )

    assert parsed.path == ["图书资料", "计算机图书", "编程语言书籍"]
    assert parsed.is_fallback is False
    assert parsed.confidence == 0.91
    assert "Rust" in parsed.reason


def test_parse_slash_separated_path():
    parsed = parse_classification_output("类别：图书资料/计算机图书/软件工程书籍")

    assert parsed.path == ["图书资料", "计算机图书", "软件工程书籍"]
    assert parsed.confidence == 0.0


def test_parse_rejects_unknown_or_incomplete_path():
    assert parse_classification_output("一级域: 图书资料\n二级类: 不存在\n三级类: 分类") is None
    assert parse_classification_output("一级域: 图书资料") is None
```

- [ ] **Step 2: Run parser tests and verify failure**

Run: `cd backend && .venv/bin/python -m pytest test/test_taxonomy_v3_llm_protocol.py -q`

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement parser**

Create `backend/app/services/taxonomy_v3_llm_protocol.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.taxonomy.universal_taxonomy_v3 import get_label_by_path


@dataclass(frozen=True)
class ParsedClassification:
    path: list[str]
    label_id: str
    is_fallback: bool
    confidence: float
    reason: str


def parse_classification_output(raw_text: str) -> ParsedClassification | None:
    text = str(raw_text or "").strip()
    if not text:
        return None

    path = _extract_line_protocol_path(text) or _extract_inline_path(text)
    if not path:
        return None

    label = get_label_by_path(path)
    if not label:
        return None

    return ParsedClassification(
        path=list(label["path"]),
        label_id=str(label["id"]),
        is_fallback=_parse_fallback_flag(text),
        confidence=_parse_confidence(text),
        reason=_parse_reason(text),
    )


def _extract_line_protocol_path(text: str) -> list[str] | None:
    fields = {}
    for line in text.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
        elif "：" in line:
            key, value = line.split("：", 1)
        else:
            continue
        fields[key.strip()] = value.strip()

    domain = fields.get("一级域")
    group = fields.get("二级类")
    leaf = fields.get("三级类")
    if domain and group and leaf:
        return [domain, group, leaf]
    return None


def _extract_inline_path(text: str) -> list[str] | None:
    cleaned = re.sub(r"^(类别|分类|路径|分类路径)\s*[:：]\s*", "", text).strip()
    parts = [part.strip() for part in cleaned.replace(">", "/").split("/") if part.strip()]
    if len(parts) == 3:
        return parts
    return None


def _parse_fallback_flag(text: str) -> bool:
    match = re.search(r"是否兜底\s*[:：]\s*(是|否|true|false|yes|no)", text, re.I)
    if not match:
        return False
    return match.group(1).lower() in {"是", "true", "yes"}


def _parse_confidence(text: str) -> float:
    match = re.search(r"置信度\s*[:：]\s*([01](?:\.\d+)?)", text)
    if not match:
        return 0.0
    return max(0.0, min(float(match.group(1)), 1.0))


def _parse_reason(text: str) -> str:
    match = re.search(r"依据\s*[:：]\s*(.+)", text)
    if not match:
        return ""
    return match.group(1).strip()[:300]
```

- [ ] **Step 4: Run parser tests and verify pass**

Run: `cd backend && .venv/bin/python -m pytest test/test_taxonomy_v3_llm_protocol.py test/test_taxonomy_v3_catalog.py -q`

Expected: PASS.

- [ ] **Step 5: Commit parser**

```bash
git add backend/app/services/taxonomy_v3_llm_protocol.py backend/test/test_taxonomy_v3_llm_protocol.py
git commit -m "feat: parse taxonomy v3 llm output"
```

### Task 3: Implement Two-Stage Taxonomy V3 Classifier

**Files:**
- Create: `backend/app/services/taxonomy_v3_classifier.py`
- Modify: `backend/app/services/taxonomy_classifier.py`
- Create: `backend/test/test_taxonomy_v3_classifier.py`
- Modify: `backend/test/test_taxonomy_classifier.py`
- Test: `backend/test/test_taxonomy_v3_classifier.py`
- Test: `backend/test/test_taxonomy_classifier.py`

- [ ] **Step 1: Write failing classifier tests**

Create `backend/test/test_taxonomy_v3_classifier.py`:

```python
import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.taxonomy_v3_classifier import TaxonomyV3Classifier  # noqa: E402


class FakeGateway:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.prompts = []

    async def call(self, prompt, task="classify", max_tokens=120, temperature=0.0, use_cache=False):
        self.prompts.append(prompt)
        content = self.outputs.pop(0)
        return type("Response", (), {"content": content})()


def test_taxonomy_v3_two_stage_classifies_programming_book():
    gateway = FakeGateway(
        [
            "一级域: 图书资料\n二级类: 综合图书\n三级类: 综合书籍\n是否兜底: 是\n置信度: 0.8\n依据: Rust 编程书籍",
            "一级域: 图书资料\n二级类: 计算机图书\n三级类: 编程语言书籍\n是否兜底: 否\n置信度: 0.93\n依据: Rust 编程和示例代码",
        ]
    )

    result = asyncio.run(
        TaxonomyV3Classifier(llm_gateway=gateway).classify(
            "doc-rust",
            "本书介绍 Rust 所有权、借用、生命周期和示例代码。",
            filename="Rust编程：入门、实战与进阶.pdf",
            file_type=".pdf",
        )
    )

    assert result["classification_path"] == ["图书资料", "计算机图书", "编程语言书籍"]
    assert result["classification_source"] == "llm_hierarchical"
    assert result["classification_issue_code"] is None
    assert result["taxonomy_version"] == "taxonomy_v3"
    assert len(gateway.prompts) == 2
    assert "候选一级域" in gateway.prompts[0]
    assert "图书资料/计算机图书/编程语言书籍" in gateway.prompts[1]


def test_taxonomy_v3_invalid_leaf_falls_back_inside_selected_domain():
    gateway = FakeGateway(
        [
            "一级域: 图书资料\n二级类: 综合图书\n三级类: 综合书籍\n是否兜底: 是\n置信度: 0.7\n依据: 文件名像图书",
            "一级域: 图书资料\n二级类: 不存在\n三级类: 不存在\n是否兜底: 否\n置信度: 0.7\n依据: 错误输出",
            "bad output",
        ]
    )

    result = asyncio.run(
        TaxonomyV3Classifier(llm_gateway=gateway).classify(
            "doc-book",
            "",
            filename="未知技术资料.pdf",
            file_type=".pdf",
        )
    )

    assert result["classification_path"] == ["图书资料", "综合图书", "综合书籍"]
    assert result["classification_source"] == "llm_hierarchical_fallback"
    assert result["classification_issue_code"] is None


def test_taxonomy_v3_llm_transport_failure_uses_filename_domain_fallback():
    class FailingGateway:
        async def call(self, *args, **kwargs):
            raise RuntimeError("network down")

    result = asyncio.run(
        TaxonomyV3Classifier(llm_gateway=FailingGateway()).classify(
            "doc-os",
            "",
            filename="操作系统导论.pdf",
            file_type=".pdf",
        )
    )

    assert result["classification_path"] == ["图书资料", "综合图书", "综合书籍"]
    assert result["classification_source"] == "llm_hierarchical_fallback"
    assert result["classification_confidence"] < 0.5
```

Modify `backend/test/test_taxonomy_classifier.py` to assert the public `TaxonomyClassifier` now returns v3 results:

```python
def test_public_taxonomy_classifier_uses_v3_hierarchical_classifier(monkeypatch):
    class FakeV3:
        async def classify(self, document_id, content, filename="", file_type=""):
            return {
                "classification_id": "books.computer.programming_language",
                "classification_leaf_id": "books.computer.programming_language",
                "classification_label": "编程语言书籍",
                "classification_path": ["图书资料", "计算机图书", "编程语言书籍"],
                "classification_domain": "图书资料",
                "classification_score": 0.91,
                "classification_confidence": 0.91,
                "classification_source": "llm_hierarchical",
                "classification_candidates": ["books.computer.programming_language"],
                "classification_review_status": "accepted",
                "classification_issue_code": None,
                "taxonomy_version": "taxonomy_v3",
            }

    import app.services.taxonomy_classifier as taxonomy_classifier_module

    monkeypatch.setattr(taxonomy_classifier_module, "TaxonomyV3Classifier", lambda llm_gateway=None: FakeV3())

    result = asyncio.run(
        taxonomy_classifier_module.TaxonomyClassifier().classify(
            "doc-1",
            "Rust 所有权和借用",
            filename="Rust编程.pdf",
            file_type=".pdf",
        )
    )

    assert result["taxonomy_version"] == "taxonomy_v3"
    assert result["classification_issue_code"] is None
```

- [ ] **Step 2: Run classifier tests and verify failure**

Run: `cd backend && .venv/bin/python -m pytest test/test_taxonomy_v3_classifier.py test/test_taxonomy_classifier.py -q`

Expected: FAIL with missing `taxonomy_v3_classifier` and public classifier still using old logic.

- [ ] **Step 3: Implement `TaxonomyV3Classifier`**

Create `backend/app/services/taxonomy_v3_classifier.py`:

```python
from __future__ import annotations

from typing import Any

from app.core.logger import logger
from app.domain.llm.gateway import LLMGateway
from app.domain.taxonomy.universal_taxonomy_v3 import (
    TAXONOMY_VERSION,
    format_path,
    get_domain_fallback,
    get_domain_options,
    get_labels_by_domain,
    infer_domain_from_filename,
)
from app.services.taxonomy_v3_llm_protocol import ParsedClassification, parse_classification_output


class TaxonomyV3Classifier:
    def __init__(self, llm_gateway: LLMGateway | None = None):
        self.llm_gateway = llm_gateway or LLMGateway()

    async def classify(self, document_id: str, content: str, filename: str = "", file_type: str = "") -> dict[str, Any]:
        del document_id
        sample = self._build_content_sample(content)
        domain = await self._select_domain(filename, file_type, sample)
        selected = await self._select_leaf(domain, filename, file_type, sample)
        if selected is None:
            return self._build_result(
                get_domain_fallback(domain),
                score=0.35,
                source="llm_hierarchical_fallback",
                is_fallback=True,
                reason="LLM 输出无法匹配合法三级目录，使用域内兜底叶子类。",
            )

        label = next(label for label in get_labels_by_domain(domain) if label["id"] == selected.label_id)
        source = "llm_hierarchical_fallback" if selected.is_fallback or label.get("fallback") else "llm_hierarchical"
        return self._build_result(
            label,
            score=selected.confidence or 0.65,
            source=source,
            is_fallback=selected.is_fallback or bool(label.get("fallback")),
            reason=selected.reason,
        )

    async def _select_domain(self, filename: str, file_type: str, sample: str) -> str:
        prompt = self._build_domain_prompt(filename, file_type, sample)
        parsed = await self._call_and_parse(prompt)
        if parsed and parsed.path[0] in get_domain_options():
            return parsed.path[0]

        retry_prompt = prompt + "\n\n只能从候选一级域中选择一个，并按固定格式返回。"
        parsed = await self._call_and_parse(retry_prompt)
        if parsed and parsed.path[0] in get_domain_options():
            return parsed.path[0]

        return infer_domain_from_filename(filename, file_type)

    async def _select_leaf(self, domain: str, filename: str, file_type: str, sample: str) -> ParsedClassification | None:
        prompt = self._build_leaf_prompt(domain, filename, file_type, sample)
        parsed = await self._call_and_parse(prompt)
        if parsed and parsed.path[0] == domain:
            return parsed

        retry_prompt = prompt + "\n\n返回路径必须完全来自候选三级目录，不得新造分类。"
        parsed = await self._call_and_parse(retry_prompt)
        if parsed and parsed.path[0] == domain:
            return parsed
        return None

    async def _call_and_parse(self, prompt: str) -> ParsedClassification | None:
        try:
            response = await self.llm_gateway.call(
                prompt,
                task="classify",
                max_tokens=160,
                temperature=0.0,
                use_cache=False,
            )
        except Exception as exc:
            logger.warning("taxonomy_v3_llm_call_failed: {}", exc)
            return None
        return parse_classification_output(response.content)

    def _build_domain_prompt(self, filename: str, file_type: str, sample: str) -> str:
        domains = "\n".join(f"- {domain}" for domain in get_domain_options())
        return (
            "你是文档分类助手。请先选择最合适的一级域。\n"
            "候选一级域：\n"
            f"{domains}\n\n"
            f"文件名: {filename}\n"
            f"扩展名: {file_type}\n"
            f"正文样本: {sample}\n\n"
            "按固定格式返回：\n"
            "一级域: <候选一级域之一>\n"
            "二级类: 综合图书\n"
            "三级类: 综合书籍\n"
            "是否兜底: 是\n"
            "置信度: 0.0到1.0\n"
            "依据: <一句话依据>"
        )

    def _build_leaf_prompt(self, domain: str, filename: str, file_type: str, sample: str) -> str:
        options = "\n".join(format_path(label) for label in get_labels_by_domain(domain))
        return (
            "你是文档分类助手。请从候选三级目录中选择一个最合适的真实路径。\n"
            f"已确定一级域: {domain}\n"
            "候选三级目录：\n"
            f"{options}\n\n"
            f"文件名: {filename}\n"
            f"扩展名: {file_type}\n"
            f"正文样本: {sample}\n\n"
            "按固定格式返回：\n"
            "一级域: <一级域>\n"
            "二级类: <候选路径中的二级类>\n"
            "三级类: <候选路径中的三级类>\n"
            "是否兜底: 是或否\n"
            "置信度: 0.0到1.0\n"
            "依据: <一句话依据>"
        )

    @staticmethod
    def _build_content_sample(content: str) -> str:
        text = str(content or "").strip()
        if len(text) <= 2400:
            return text
        head = text[:2400]
        middle_start = max(0, len(text) // 2 - 400)
        middle = text[middle_start : middle_start + 800]
        tail = text[-800:]
        return "\n".join([head, middle, tail])

    @staticmethod
    def _build_result(label: dict[str, Any], *, score: float, source: str, is_fallback: bool, reason: str) -> dict[str, Any]:
        path = list(label.get("path") or [])
        confidence = round(max(0.0, min(float(score), 1.0)), 4)
        return {
            "classification_id": label.get("id", ""),
            "classification_leaf_id": label.get("id", ""),
            "classification_label": label.get("label", ""),
            "classification_path": path,
            "classification_domain": path[0] if path else None,
            "classification_score": confidence,
            "classification_confidence": confidence,
            "classification_source": source,
            "classification_candidates": [label.get("id", "")],
            "classification_review_status": "accepted",
            "classification_issue_code": None,
            "classification_is_fallback": bool(is_fallback),
            "classification_reason": str(reason or "")[:300],
            "taxonomy_version": TAXONOMY_VERSION,
        }
```

- [ ] **Step 4: Delegate public `TaxonomyClassifier` to v3**

Modify `backend/app/services/taxonomy_classifier.py` so the existing class becomes a thin wrapper:

```python
from __future__ import annotations

from app.domain.llm.gateway import LLMGateway
from app.services.taxonomy_v3_classifier import TaxonomyV3Classifier


class TaxonomyClassifier:
    def __init__(self, llm_gateway: LLMGateway | None = None):
        self._classifier = TaxonomyV3Classifier(llm_gateway=llm_gateway)

    async def classify(self, document_id: str, content: str, filename: str = "", file_type: str = "") -> dict:
        return await self._classifier.classify(
            document_id=document_id,
            content=content,
            filename=filename,
            file_type=file_type,
        )
```

- [ ] **Step 5: Run classifier tests and update old expectations**

Run: `cd backend && .venv/bin/python -m pytest test/test_taxonomy_v3_classifier.py test/test_taxonomy_classifier.py -q`

Expected: PASS after updating old tests that asserted `no_match`. Replace those assertions with v3 fallback assertions:

```python
assert result["taxonomy_version"] == "taxonomy_v3"
assert result["classification_path"]
assert result["classification_issue_code"] is None
```

- [ ] **Step 6: Commit classifier**

```bash
git add backend/app/services/taxonomy_v3_classifier.py backend/app/services/taxonomy_classifier.py backend/test/test_taxonomy_v3_classifier.py backend/test/test_taxonomy_classifier.py
git commit -m "feat: classify documents with taxonomy v3"
```

### Task 4: Wire Taxonomy V3 Persistence And Document API Metadata

**Files:**
- Modify: `backend/app/services/classification_service.py`
- Modify: `backend/api/document.py`
- Modify: `backend/test/test_classification_service_v2.py`
- Modify: `backend/test/test_document_reader_api.py`
- Test: `backend/test/test_classification_service_v2.py`
- Test: `backend/test/test_document_reader_api.py`

- [ ] **Step 1: Write failing persistence test**

Append to `backend/test/test_classification_service_v2.py`:

```python
def test_classification_service_persists_taxonomy_v3_without_no_match(monkeypatch):
    monkeypatch.setattr(
        classification_service_module,
        "get_document_info",
        lambda document_id: {"id": document_id, "filename": "Rust编程.pdf", "file_type": ".pdf"},
    )
    monkeypatch.setattr(
        classification_service_module,
        "get_document_content_record",
        lambda document_id: {"full_content": "Rust 所有权 借用 生命周期 示例代码"},
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
                "classification_id": "books.computer.programming_language",
                "classification_leaf_id": "books.computer.programming_language",
                "classification_label": "编程语言书籍",
                "classification_path": ["图书资料", "计算机图书", "编程语言书籍"],
                "classification_domain": "图书资料",
                "classification_score": 0.91,
                "classification_confidence": 0.91,
                "classification_source": "llm_hierarchical",
                "classification_candidates": ["books.computer.programming_language"],
                "classification_review_status": "accepted",
                "classification_issue_code": None,
                "classification_is_fallback": False,
                "classification_reason": "Rust 编程书籍",
                "taxonomy_version": "taxonomy_v3",
            }

    monkeypatch.setattr(classification_service_module, "TaxonomyClassifier", FakeTaxonomyClassifier)

    result = ClassificationService().classify("doc-rust")

    assert result["topic_path"] == ["图书资料", "计算机图书", "编程语言书籍"]
    assert result["taxonomy_version"] == "taxonomy_v3"
    assert updates[0]["classification_issue_code"] is None
    assert updates[0]["classification_source"] == "llm_hierarchical"
```

Append to `backend/test/test_document_reader_api.py` or create a focused API response test:

```python
def test_document_response_includes_taxonomy_v3_metadata():
    from api.document import _build_document_response

    payload = _build_document_response(
        {
            "id": "doc-rust",
            "filename": "Rust编程.pdf",
            "file_type": ".pdf",
            "classification_leaf_id": "books.computer.programming_language",
            "classification_domain": "图书资料",
            "classification_confidence": 0.91,
            "taxonomy_version": "taxonomy_v3",
        }
    )

    assert payload["classification_leaf_id"] == "books.computer.programming_language"
    assert payload["classification_domain"] == "图书资料"
    assert payload["classification_confidence"] == 0.91
    assert payload["taxonomy_version"] == "taxonomy_v3"
```

- [ ] **Step 2: Run persistence tests and verify failure**

Run: `cd backend && .venv/bin/python -m pytest test/test_classification_service_v2.py test/test_document_reader_api.py -q`

Expected: FAIL because document API does not expose v3 metadata and service serialization may not include all fallback fields.

- [ ] **Step 3: Update serialization and save logic**

Modify `ClassificationService._serialize_taxonomy_assignment()` to include optional fields:

```python
"classification_is_fallback": bool(result.get("classification_is_fallback", False)),
"classification_reason": result.get("classification_reason"),
```

Modify `ClassificationService._save_taxonomy_result()` to keep v3 fields that already fit the existing schema and avoid clearing source for fallback labels:

```python
"classification_source": result.get("classification_source"),
"classification_issue_code": result.get("classification_issue_code"),
"taxonomy_version": result.get("taxonomy_version", "taxonomy_v1"),
```

Do not add database columns for `classification_is_fallback` or `classification_reason` in this task. Frontend fallback display uses `classification_source=llm_hierarchical_fallback`.

- [ ] **Step 4: Expose v3 metadata in document API**

Modify `backend/api/document.py` `_build_document_response()`:

```python
"classification_leaf_id": payload.get("classification_leaf_id"),
"classification_domain": payload.get("classification_domain"),
"classification_confidence": payload.get("classification_confidence"),
"taxonomy_version": payload.get("taxonomy_version"),
```

- [ ] **Step 5: Run persistence tests and verify pass**

Run: `cd backend && .venv/bin/python -m pytest test/test_classification_service_v2.py test/test_document_reader_api.py -q`

Expected: PASS.

- [ ] **Step 6: Commit persistence wiring**

```bash
git add backend/app/services/classification_service.py backend/api/document.py backend/test/test_classification_service_v2.py backend/test/test_document_reader_api.py
git commit -m "feat: persist taxonomy v3 assignments"
```

### Task 5: Add Explicit Batch Reclassification

**Files:**
- Modify: `backend/app/schemas/classification.py`
- Modify: `backend/app/services/classification_service.py`
- Modify: `backend/api/classification.py`
- Create: `backend/test/test_batch_reclassification.py`
- Test: `backend/test/test_batch_reclassification.py`

- [ ] **Step 1: Write failing batch tests**

Create `backend/test/test_batch_reclassification.py`:

```python
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.classification as classification_api  # noqa: E402
import app.services.classification_service as classification_service_module  # noqa: E402
from app.services.classification_service import ClassificationService  # noqa: E402


def test_batch_reclassify_filters_no_match_documents(monkeypatch):
    monkeypatch.setattr(
        classification_service_module,
        "get_all_documents",
        lambda: [
            {"id": "doc-1", "filename": "Rust编程.pdf", "classification_issue_code": "no_match"},
            {"id": "doc-2", "filename": "ready.pdf", "classification_issue_code": None},
        ],
    )

    service = ClassificationService()
    called = []
    service.reclassify = lambda document_id, schedule_topic_tree_update=False: called.append(document_id) or {
        "document_id": document_id,
        "taxonomy_version": "taxonomy_v3",
    }

    result = service.batch_reclassify({"issue_codes": ["no_match"]})

    assert result["total"] == 1
    assert result["success_count"] == 1
    assert called == ["doc-1"]
    assert result["items"][0]["document_id"] == "doc-1"


def test_batch_reclassify_accepts_explicit_document_ids(monkeypatch):
    monkeypatch.setattr(
        classification_service_module,
        "get_all_documents",
        lambda: [
            {"id": "doc-1", "filename": "Rust编程.pdf"},
            {"id": "doc-2", "filename": "操作系统导论.pdf"},
        ],
    )

    service = ClassificationService()
    called = []
    service.reclassify = lambda document_id, schedule_topic_tree_update=False: called.append(document_id) or {
        "document_id": document_id,
        "taxonomy_version": "taxonomy_v3",
    }

    result = service.batch_reclassify({"document_ids": ["doc-2"]})

    assert result["total"] == 1
    assert called == ["doc-2"]


def test_batch_reclassify_api_delegates_to_service(monkeypatch):
    called = {}

    class FakeService:
        def batch_reclassify(self, filters):
            called["filters"] = filters
            return {"total": 1, "success_count": 1, "failed_count": 0, "items": []}

    monkeypatch.setattr(classification_api, "classification_service", FakeService())

    import asyncio

    response = asyncio.run(
        classification_api.batch_reclassify_documents(
            classification_api.BatchReclassifyRequest(issue_codes=["no_match"])
        )
    )

    assert called["filters"]["issue_codes"] == ["no_match"]
    assert response["data"]["success_count"] == 1
```

- [ ] **Step 2: Run batch tests and verify failure**

Run: `cd backend && .venv/bin/python -m pytest test/test_batch_reclassification.py -q`

Expected: FAIL because `BatchReclassifyRequest` and `batch_reclassify` do not exist.

- [ ] **Step 3: Add request schema**

Modify `backend/app/schemas/classification.py`:

```python
class BatchReclassifyRequest(BaseModel):
    document_ids: List[str] = Field(default_factory=list)
    issue_codes: List[str] = Field(default_factory=list)
    taxonomy_versions: List[str] = Field(default_factory=list)
    file_types: List[str] = Field(default_factory=list)
    limit: int = 100
```

- [ ] **Step 4: Implement service method**

Add to `ClassificationService`:

```python
def batch_reclassify(self, filters: Dict) -> Dict:
    documents = list(get_all_documents())
    selected = self._select_documents_for_reclassification(documents, filters)
    items = []
    success_count = 0
    failed_count = 0

    for doc in selected:
        document_id = doc.get("id") or doc.get("document_id")
        if not document_id:
            continue
        try:
            old_snapshot = {
                "classification_result": doc.get("classification_result"),
                "classification_path": doc.get("classification_path"),
                "classification_issue_code": doc.get("classification_issue_code"),
                "taxonomy_version": doc.get("taxonomy_version"),
            }
            payload = self.reclassify(document_id, schedule_topic_tree_update=False)
            success_count += 1
            items.append({"document_id": document_id, "status": "success", "old": old_snapshot, "new": payload})
        except Exception as exc:
            failed_count += 1
            items.append({"document_id": document_id, "status": "failed", "error": str(exc)})

    return {
        "total": len(selected),
        "success_count": success_count,
        "failed_count": failed_count,
        "items": items,
    }


@staticmethod
def _select_documents_for_reclassification(documents: List[Dict], filters: Dict) -> List[Dict]:
    document_ids = set(filters.get("document_ids") or [])
    issue_codes = set(filters.get("issue_codes") or [])
    taxonomy_versions = set(filters.get("taxonomy_versions") or [])
    file_types = {str(item or "").lower() for item in filters.get("file_types") or []}
    limit = int(filters.get("limit") or 100)

    selected = []
    for doc in documents:
        doc_id = doc.get("id") or doc.get("document_id")
        if document_ids and doc_id not in document_ids:
            continue
        if issue_codes and doc.get("classification_issue_code") not in issue_codes:
            continue
        if taxonomy_versions and doc.get("taxonomy_version") not in taxonomy_versions:
            continue
        if file_types and str(doc.get("file_type") or "").lower() not in file_types:
            continue
        selected.append(doc)
        if len(selected) >= limit:
            break
    return selected
```

- [ ] **Step 5: Add API route**

Modify `backend/api/classification.py` imports:

```python
from app.schemas.classification import BatchReclassifyRequest
```

Add route:

```python
@router.post("/reclassify/batch", summary="批量重新分类文档")
async def batch_reclassify_documents(request: BatchReclassifyRequest):
    try:
        result = await _run_blocking_classification(
            lambda: classification_service.batch_reclassify(request.dict())
        )
        return success(data=result, message=f"批量重新分类完成，成功 {result['success_count']}/{result['total']}")
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)
```

- [ ] **Step 6: Run batch tests and verify pass**

Run: `cd backend && .venv/bin/python -m pytest test/test_batch_reclassification.py -q`

Expected: PASS.

- [ ] **Step 7: Commit batch reclassification**

```bash
git add backend/app/schemas/classification.py backend/app/services/classification_service.py backend/api/classification.py backend/test/test_batch_reclassification.py
git commit -m "feat: add batch reclassification"
```

### Task 6: Update `/documents` Classification Display

**Files:**
- Modify: `frontend/docagent-frontend/src/api/index.js`
- Modify: `frontend/docagent-frontend/src/components/FileList.vue`
- Modify: `frontend/docagent-frontend/src/components/__tests__/FileList.spec.js`
- Test: `frontend/docagent-frontend/src/components/__tests__/FileList.spec.js`

- [ ] **Step 1: Write failing frontend tests**

Modify `frontend/docagent-frontend/src/components/__tests__/FileList.spec.js`:

```javascript
it('shows taxonomy v3 fallback as real path instead of unclassified', () => {
  const wrapper = mountFileList()

  expect(
    wrapper.vm.getClassificationText({
      taxonomy_version: 'taxonomy_v3',
      classification_path: ['图书资料', '综合图书', '综合书籍'],
      classification_source: 'llm_hierarchical_fallback',
      classification_issue_code: null
    })
  ).toBe('图书资料 > 综合图书 > 综合书籍')

  expect(wrapper.vm.getClassificationSourceMeta('llm_hierarchical')).toEqual({ label: 'AI', tone: 'ai' })
  expect(wrapper.vm.getClassificationSourceMeta('llm_hierarchical_fallback')).toEqual({ label: '兜底分类', tone: 'fallback' })
})

it('does not render stale ready-state local index errors in classification details', () => {
  const wrapper = mountFileList()

  expect(
    wrapper.vm.getClassificationErrorDetails({
      local_index_status: 'ready',
      local_index_error: 'Unsupported file type: .xlsx',
      ingest_error: ''
    })
  ).toEqual([])

  expect(
    wrapper.vm.getClassificationErrorDetails({
      local_index_status: 'failed',
      local_index_error: 'parser failed',
      ingest_error: 'RetryError[x]'
    })
  ).toEqual(['RetryError[x]', 'parser failed'])
})
```

- [ ] **Step 2: Run frontend tests and verify failure**

Run: `cd frontend/docagent-frontend && npm test -- --run src/components/__tests__/FileList.spec.js`

Expected: FAIL because `getClassificationErrorDetails` and v3 source metadata are missing.

- [ ] **Step 3: Add frontend API method**

Modify `frontend/docagent-frontend/src/api/index.js`:

```javascript
batchReclassifyDocuments: (payload = {}) => {
  return request.post('/classification/reclassify/batch', payload)
},
```

- [ ] **Step 4: Update classification text and source badges**

Modify `FileList.vue`:

```javascript
const getClassificationText = (row) => {
  const path = parseClassificationPath(row.classification_path)
  if (path.length) return path.join(' > ')
  if (row.taxonomy_version === 'taxonomy_v3' && row.classification_result) {
    return row.classification_result
  }
  if (row.classification_issue_code === 'pending_local_content') {
    return '待本地索引'
  }
  if (row.classification_issue_code === 'no_match') {
    return '未分类'
  }
  return row.classification_result || '未分类'
}
```

Extend source metadata:

```javascript
llm_hierarchical: { label: 'AI', tone: 'ai' },
llm_hierarchical_fallback: { label: '兜底分类', tone: 'fallback' },
```

Add helper:

```javascript
const getClassificationErrorDetails = (row) => {
  const details = []
  if (row.ingest_error) details.push(row.ingest_error)
  if (row.local_index_error && row.local_index_status !== 'ready') {
    details.push(row.local_index_error)
  }
  return details
}
```

Replace template error paragraphs under classification with:

```vue
<p
  v-for="detail in getClassificationErrorDetails(row)"
  :key="detail"
  class="ingest-error"
>
  {{ detail }}
</p>
```

- [ ] **Step 5: Run frontend tests and verify pass**

Run: `cd frontend/docagent-frontend && npm test -- --run src/components/__tests__/FileList.spec.js`

Expected: PASS.

- [ ] **Step 6: Commit frontend display changes**

```bash
git add frontend/docagent-frontend/src/api/index.js frontend/docagent-frontend/src/components/FileList.vue frontend/docagent-frontend/src/components/__tests__/FileList.spec.js
git commit -m "feat: display taxonomy v3 classifications"
```

### Task 7: Focused End-to-End Verification

**Files:**
- Test only

- [ ] **Step 1: Run backend taxonomy and classification tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest \
  test/test_taxonomy_v3_catalog.py \
  test/test_taxonomy_v3_llm_protocol.py \
  test/test_taxonomy_v3_classifier.py \
  test/test_taxonomy_classifier.py \
  test/test_classification_service_v2.py \
  test/test_batch_reclassification.py \
  test/test_document_reader_api.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run backend related regression tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest \
  test/test_document_label_resolver.py \
  test/test_classification_topic_tree_contract.py \
  test/test_taxonomy_v2_storage.py \
  test/test_taxonomy_migrations.py \
  -q
```

Expected: PASS.

- [ ] **Step 3: Run frontend focused tests**

Run:

```bash
cd frontend/docagent-frontend && npm test -- --run src/components/__tests__/FileList.spec.js
```

Expected: PASS.

- [ ] **Step 4: Manual API smoke test for one document**

Run after starting the backend:

```bash
curl -s -X POST http://localhost:6008/api/v1/classification/reclassify/batch \
  -H 'Content-Type: application/json' \
  -d '{"issue_codes":["no_match"],"limit":5}' | python -m json.tool
```

Expected response shape:

```json
{
  "code": 0,
  "message": "批量重新分类完成，成功 5/5",
  "data": {
    "total": 5,
    "success_count": 5,
    "failed_count": 0,
    "items": []
  }
}
```

- [ ] **Step 5: Final status check**

Run:

```bash
git status --short
```

Expected: only intentional files remain modified. No generated logs, runtime database files, or `__pycache__` files should be staged.
