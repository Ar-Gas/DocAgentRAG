from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
FORBIDDEN_IMPORTS = [
    "utils.classifier",
    "utils.multi_level_classifier",
    "app.services.legacy_classification_tree_bridge",
]


def test_legacy_classification_engine_files_are_deleted():
    assert not (BACKEND_DIR / "utils" / "classifier.py").exists()
    assert not (BACKEND_DIR / "utils" / "multi_level_classifier.py").exists()
    assert not (BACKEND_DIR / "app" / "services" / "legacy_classification_tree_bridge.py").exists()


def test_backend_no_longer_imports_legacy_classification_modules():
    offenders = []

    for file_path in (BACKEND_DIR / "app").rglob("*.py"):
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        if any(pattern in content for pattern in FORBIDDEN_IMPORTS):
            offenders.append(str(file_path.relative_to(BACKEND_DIR)))

    for file_path in (BACKEND_DIR / "api").rglob("*.py"):
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        if any(pattern in content for pattern in FORBIDDEN_IMPORTS):
            offenders.append(str(file_path.relative_to(BACKEND_DIR)))

    main_py = BACKEND_DIR / "main.py"
    main_content = main_py.read_text(encoding="utf-8", errors="ignore")
    if any(pattern in main_content for pattern in FORBIDDEN_IMPORTS):
        offenders.append("main.py")

    assert offenders == [], f"unexpected legacy classification imports remain: {offenders}"


def test_document_vector_index_service_drops_legacy_classification_hooks():
    content = (BACKEND_DIR / "app" / "services" / "document_vector_index_service.py").read_text(
        encoding="utf-8",
        errors="ignore",
    )

    assert "classification_bridge_add" not in content
    assert "classification_bridge_delete" not in content
    assert "list_document_chunk_embeddings" not in content


def test_classification_service_keeps_only_topic_tree_classification_logic():
    content = (BACKEND_DIR / "app" / "services" / "classification_service.py").read_text(
        encoding="utf-8",
        errors="ignore",
    )

    assert "get_chroma_collection" not in content
    assert "DocumentVectorIndexService" not in content
    assert "category_batch_rechunk" not in content


def test_document_pipeline_and_vector_store_remove_legacy_chunk_collection():
    document_service_content = (BACKEND_DIR / "app" / "services" / "document_service.py").read_text(
        encoding="utf-8",
        errors="ignore",
    )
    vector_store_content = (BACKEND_DIR / "app" / "infra" / "vector_store.py").read_text(
        encoding="utf-8",
        errors="ignore",
    )

    assert "get_chroma_collection" not in document_service_content
    assert "save_document_to_chroma" not in document_service_content
    assert "re_chunk_document" not in document_service_content
    assert "_trigger_block_reindex_best_effort" not in document_service_content
    assert 'name="documents"' not in vector_store_content
    assert "get_chroma_collection" not in vector_store_content
