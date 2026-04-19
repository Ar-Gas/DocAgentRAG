import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import run_lightrag_server  # noqa: E402


def test_main_applies_runtime_patch_before_server_main(monkeypatch):
    calls = []

    def fake_apply_runtime_patch():
        calls.append("patch")

    def fake_server_main():
        calls.append("server")
        return 7

    monkeypatch.setattr(run_lightrag_server, "apply_runtime_patch", fake_apply_runtime_patch)
    monkeypatch.setattr(run_lightrag_server, "server_main", fake_server_main)

    result = run_lightrag_server.main()

    assert result == 7
    assert calls == ["patch", "server"]
