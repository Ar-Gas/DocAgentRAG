from api import router as root_router


def test_removed_semantic_routes_are_absent_from_root_router():
    paths = {route.path for route in root_router.routes if hasattr(route, "path")}

    assert "/classification/reclassify/{document_id}" not in paths
    assert "/classification/topic-tree" not in paths
    assert "/classification/topic-tree/build" not in paths
    assert "/classification/tables/generate" not in paths
    assert "/retrieval/expand-query" not in paths
    assert "/retrieval/llm-status" not in paths
    assert "/retrieval/summarize-results" not in paths
    assert "/retrieval/smart-search" not in paths
    assert "/retrieval/workspace-search-stream" not in paths
