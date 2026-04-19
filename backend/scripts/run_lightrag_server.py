from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.lightrag_runtime_patch import apply_runtime_patch


def server_main() -> int:
    from lightrag.api.lightrag_server import main as _server_main

    return _server_main()


def main() -> int:
    apply_runtime_patch()
    return server_main()


if __name__ == "__main__":
    raise SystemExit(main())
