import os
import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import dev_supervisor


def test_backend_target_starts_three_independent_services():
    services = dev_supervisor.expand_target("backend")

    assert [service.name for service in services] == ["local_embedding", "lightrag", "api"]
    assert services[0].health_url == "http://127.0.0.1:8011/health"
    assert services[1].health_url == "http://127.0.0.1:9621/health"
    assert services[2].health_url == "http://127.0.0.1:6008/health"
    assert services[1].env["EMBEDDING_TIMEOUT"] == "120"
    assert services[1].env["EMBEDDING_BATCH_NUM"] == "1"
    assert services[1].env["EMBEDDING_FUNC_MAX_ASYNC"] == "1"
    assert services[1].env["MAX_PARALLEL_INSERT"] == "1"
    assert services[1].env["MAX_ASYNC"] == "1"
    assert services[1].env["EMBEDDING_DIM"] == "384"
    assert services[1].env["EMBEDDING_MODEL"] == "all-MiniLM-L6-v2"
    assert services[1].env["WORKING_DIR"].endswith("backend/data/lightrag/all-MiniLM-L6-v2-384d")
    assert {"LOCAL_EMBEDDING_AUTO_START": "false", "LIGHTRAG_AUTO_START": "false"}.items() <= services[2].env.items()


def test_dev_supervisor_script_entrypoint_imports_from_repo_root():
    result = subprocess.run(
        [sys.executable, str(dev_supervisor.BACKEND_DIR / "scripts" / "dev_supervisor.py"), "--help"],
        cwd=str(dev_supervisor.REPO_ROOT),
        text=True,
        capture_output=True,
        timeout=5,
    )

    assert result.returncode == 0
    assert "DocAgentRAG local development supervisor" in result.stdout


def test_all_target_adds_frontend_after_backend_services():
    services = dev_supervisor.expand_target("all")

    assert [service.name for service in services] == ["local_embedding", "lightrag", "api", "frontend"]
    assert services[-1].health_url == "http://127.0.0.1:3000/"


def test_log_paths_are_grouped_by_service(tmp_path):
    runtime = dev_supervisor.RuntimeLayout(repo_root=tmp_path)

    assert runtime.log_file("api").parent == tmp_path / "logs" / "api"
    assert runtime.log_file("lightrag").name == "current.log"
    assert runtime.pid_file("frontend") == tmp_path / ".runtime" / "pids" / "frontend.pid"


def test_cleanup_logs_removes_old_files_and_enforces_byte_budget(tmp_path):
    log_dir = tmp_path / ".runtime" / "logs" / "api"
    log_dir.mkdir(parents=True)
    old_file = log_dir / "old.log"
    old_file.write_text("old", encoding="utf-8")
    old_time = time.time() - 10 * 24 * 60 * 60
    os.utime(old_file, (old_time, old_time))

    large_one = log_dir / "large-one.log"
    large_two = log_dir / "large-two.log"
    large_one.write_text("a" * 70, encoding="utf-8")
    time.sleep(0.01)
    large_two.write_text("b" * 70, encoding="utf-8")

    dev_supervisor.cleanup_logs(
        log_dir,
        retention_days=7,
        max_bytes=100,
        now=time.time(),
    )

    assert not old_file.exists()
    assert large_two.exists()
    assert sum(path.stat().st_size for path in log_dir.glob("*.log")) <= 100


def test_health_ok_requires_json_status_healthy_when_present(monkeypatch):
    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return b'{"status":"warming_up","readiness":"warming_up"}'

        def headers(self):
            return {}

    monkeypatch.setattr(dev_supervisor, "urlopen", lambda request, timeout: FakeResponse())

    assert dev_supervisor.health_ok("http://127.0.0.1:8011/health") is False


def test_health_ok_accepts_json_status_healthy(monkeypatch):
    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return b'{"status":"healthy","readiness":"ready"}'

        def headers(self):
            return {}

    monkeypatch.setattr(dev_supervisor, "urlopen", lambda request, timeout: FakeResponse())

    assert dev_supervisor.health_ok("http://127.0.0.1:8011/health") is True


def test_start_is_idempotent_for_already_managed_open_ports(tmp_path, monkeypatch):
    runtime_dir = tmp_path / ".runtime"
    layout = dev_supervisor.RuntimeLayout(repo_root=tmp_path, runtime_dir=runtime_dir)
    layout.ensure()
    layout.pid_file("api").write_text("12345", encoding="utf-8")
    service = dev_supervisor.ServiceSpec(
        name="api",
        command=["unused"],
        cwd=tmp_path,
        port=6008,
        health_url="http://127.0.0.1:6008/health",
    )
    started_services = []

    monkeypatch.setenv("DOUBAO_API_KEY", "test-key")
    monkeypatch.setattr(dev_supervisor, "backend_python", lambda: Path(sys.executable))
    monkeypatch.setattr(dev_supervisor, "expand_target", lambda target: [service])
    monkeypatch.setattr(dev_supervisor, "port_open", lambda port: True)
    monkeypatch.setattr(dev_supervisor, "is_process_running", lambda pid: pid == 12345)
    monkeypatch.setattr(
        dev_supervisor,
        "start_service",
        lambda service, layout, force=False: started_services.append(service.name) or 0,
    )

    args = argparse.Namespace(target="api", runtime_dir=str(runtime_dir), force=False, skip_preflight=False)

    assert dev_supervisor.command_start(args) == 0
    assert started_services == ["api"]


def test_is_process_running_treats_zombie_as_not_running(monkeypatch):
    zombie_state = "Name:\tpython\nState:\tZ (zombie)\n"

    monkeypatch.setattr(dev_supervisor.os, "kill", lambda pid, sig: None)
    monkeypatch.setattr(Path, "exists", lambda self: str(self) == "/proc/43210/status")
    monkeypatch.setattr(Path, "read_text", lambda self, encoding="utf-8": zombie_state)

    assert dev_supervisor.is_process_running(43210) is False
