# DocAgent Modular Classification And Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move classification and operational runtime behavior into dedicated modules so document labels, review states, health, audits, and repair operations stop living inside oversized service files and startup hooks.

**Architecture:** Classification becomes a version-bound business module that reads documents through contracts and persists reviewable label assignments. Runtime becomes the only place for health, dependency status, audits, and repair entry points. `main.py` returns to lightweight process startup instead of owning reconciliation logic.

**Tech Stack:** FastAPI, sqlite3, pytest, asyncio

---

## File Structure

**Files:**
- Create: `backend/app/modules/classification/api.py`
- Create: `backend/app/modules/classification/schemas.py`
- Create: `backend/app/modules/classification/service.py`
- Create: `backend/app/modules/classification/taxonomy.py`
- Create: `backend/app/modules/classification/contracts.py`
- Create: `backend/app/modules/classification/README.md`
- Create: `backend/app/modules/runtime/api.py`
- Create: `backend/app/modules/runtime/service.py`
- Create: `backend/app/modules/runtime/health.py`
- Create: `backend/app/modules/runtime/audit.py`
- Create: `backend/app/modules/runtime/repair.py`
- Create: `backend/app/modules/runtime/contracts.py`
- Create: `backend/app/modules/runtime/README.md`
- Modify: `backend/api/classification.py`
- Modify: `backend/api/admin.py`
- Modify: `backend/main.py`
- Create: `backend/test/modules/classification/test_classification_service_contract.py`
- Create: `backend/test/modules/runtime/test_runtime_service_contract.py`

---

### Task 1: Build The Classification Module With Version-Bound Assignments

**Files:**
- Create: `backend/app/modules/classification/api.py`
- Create: `backend/app/modules/classification/schemas.py`
- Create: `backend/app/modules/classification/service.py`
- Create: `backend/app/modules/classification/taxonomy.py`
- Create: `backend/app/modules/classification/contracts.py`
- Create: `backend/app/modules/classification/README.md`
- Create: `backend/test/modules/classification/test_classification_service_contract.py`

- [ ] **Step 1: Write the failing classification test**

Create `backend/test/modules/classification/test_classification_service_contract.py` with:

```python
from app.modules.classification.service import ClassificationService


def test_classification_service_binds_result_to_version():
    service = ClassificationService(
        document_lookup=lambda document_id: {"document_id": document_id, "active_version_id": "ver-1", "filename": "report.pdf"},
        saver=lambda payload: payload,
        classifier=lambda payload: {"label": "研究报告", "confidence": 0.92, "source": "lightrag+llm"},
    )

    result = service.classify("doc-1")

    assert result.version_id == "ver-1"
    assert result.label == "研究报告"
```

- [ ] **Step 2: Run the classification test and verify it fails**

Run: `cd backend && python -m pytest test/modules/classification/test_classification_service_contract.py::test_classification_service_binds_result_to_version -v`
Expected: FAIL because the module does not exist yet.

- [ ] **Step 3: Implement the classification module**

Create `backend/app/modules/classification/schemas.py` with:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ClassificationView:
    document_id: str
    version_id: str
    label: str
    confidence: float
    source: str
```

Implement `ClassificationService.classify` so it always persists classification rows against the active `version_id`, not just the document id.

- [ ] **Step 4: Re-run the classification test**

Run: `cd backend && python -m pytest test/modules/classification/test_classification_service_contract.py::test_classification_service_binds_result_to_version -v`
Expected: PASS.

- [ ] **Step 5: Commit the classification module**

```bash
git add backend/app/modules/classification backend/test/modules/classification/test_classification_service_contract.py
git commit -m "feat: add modular classification service"
```

### Task 2: Build The Runtime Module For Health, Audit, And Repair

**Files:**
- Create: `backend/app/modules/runtime/api.py`
- Create: `backend/app/modules/runtime/service.py`
- Create: `backend/app/modules/runtime/health.py`
- Create: `backend/app/modules/runtime/audit.py`
- Create: `backend/app/modules/runtime/repair.py`
- Create: `backend/app/modules/runtime/contracts.py`
- Create: `backend/app/modules/runtime/README.md`
- Create: `backend/test/modules/runtime/test_runtime_service_contract.py`

- [ ] **Step 1: Write the failing runtime service test**

Create `backend/test/modules/runtime/test_runtime_service_contract.py` with:

```python
import pytest

from app.modules.runtime.service import RuntimeService


class DummyGateway:
    async def search(self, request):
        return None


@pytest.mark.asyncio
async def test_runtime_service_reports_dependency_health():
    service = RuntimeService(
        dependency_probes={
            "sqlite": lambda: {"status": "healthy"},
            "lightrag": lambda: {"status": "healthy"},
            "filesystem": lambda: {"status": "healthy"},
        }
    )

    health = await service.health()

    assert health["dependencies"]["lightrag"]["status"] == "healthy"
```

- [ ] **Step 2: Run the runtime service test and verify it fails**

Run: `cd backend && python -m pytest test/modules/runtime/test_runtime_service_contract.py::test_runtime_service_reports_dependency_health -v`
Expected: FAIL because the runtime module does not exist yet.

- [ ] **Step 3: Implement the runtime module**

Implement `RuntimeService.health`, `RuntimeService.audit`, and `RuntimeService.repair` with explicit dependency probes and persisted audit records. Expose them through `/api/v2/runtime/*`.

- [ ] **Step 4: Re-run the runtime service test**

Run: `cd backend && python -m pytest test/modules/runtime/test_runtime_service_contract.py::test_runtime_service_reports_dependency_health -v`
Expected: PASS.

- [ ] **Step 5: Commit the runtime module**

```bash
git add backend/app/modules/runtime backend/test/modules/runtime/test_runtime_service_contract.py
git commit -m "feat: add modular runtime service"
```

### Task 3: Route v1 Classification And Admin APIs Through Compatibility Shims

**Files:**
- Modify: `backend/api/classification.py`
- Modify: `backend/api/admin.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Add targeted compatibility assertions**

Extend existing API tests with:

```python
def test_classification_response_contains_version_id(client):
    response = client.post("/api/v1/classification/classify", json={"document_id": "doc-1"})
    assert response.status_code in {200, 400}
    if response.status_code == 200:
        assert "version_id" in response.json()["data"]
```

```python
def test_admin_health_routes_through_runtime_module(client):
    response = client.get("/api/v1/admin/health")
    assert response.status_code == 200
    assert "checks" in response.json()["data"] or "checks" in response.json()
```

- [ ] **Step 2: Run the targeted compatibility tests**

Run: `cd backend && python -m pytest test/test_classification_topic_tree_contract.py test/test_observability.py -v`
Expected: at least one failure or missing field before wiring.

- [ ] **Step 3: Delegate to modular services**

Update `backend/api/classification.py` and `backend/api/admin.py` to instantiate and call the modular services, mapping their outputs into the current response shape. Remove heavy reconciliation from `main.py` startup and expose it as runtime repair/audit operations instead.

- [ ] **Step 4: Re-run the targeted compatibility tests**

Run: `cd backend && python -m pytest test/test_classification_topic_tree_contract.py test/test_observability.py -v`
Expected: PASS.

- [ ] **Step 5: Commit the compatibility wiring**

```bash
git add backend/api/classification.py backend/api/admin.py backend/main.py backend/test/test_classification_topic_tree_contract.py backend/test/test_observability.py
git commit -m "refactor: route classification and admin flows through modular runtime"
```

## Verification

- [ ] Run: `cd backend && python -m pytest test/modules/classification test/modules/runtime -v`
- [ ] Run: `cd backend && python -m pytest test/test_classification_topic_tree_contract.py test/test_admin_document_import_api.py test/test_observability.py -v`
- [ ] Manually confirm:

```text
1. Classification rows are tied to version_id.
2. Runtime health reports liveness, readiness, and dependency checks.
3. Startup no longer launches long reconciliation tasks in-process.
4. Existing admin and classification routes still respond.
```
