from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
FORBIDDEN_IMPORT = "utils" + ".storage"


def test_backend_no_longer_depends_on_storage_facade():
    legacy_storage_path = BACKEND_DIR / "utils" / "storage.py"
    assert not legacy_storage_path.exists(), "legacy storage facade should be deleted after dependency migration"

    offenders = []
    for file_path in BACKEND_DIR.rglob("*.py"):
        if file_path == Path(__file__).resolve():
            continue
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        if FORBIDDEN_IMPORT in content:
            offenders.append(str(file_path.relative_to(BACKEND_DIR)))

    assert offenders == [], f"unexpected legacy storage imports remain: {offenders}"
