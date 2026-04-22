from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
from urllib.error import URLError
from urllib.request import Request, urlopen

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.lightrag_dev_config import build_lightrag_env
from config import (
    DOUBAO_API_KEY,
    DOUBAO_DEFAULT_LLM_MODEL,
    DOUBAO_LLM_API_URL,
    LOCAL_EMBEDDING_DIM,
    LOCAL_EMBEDDING_MODEL_NAME,
)

REPO_ROOT = BACKEND_DIR.parent
FRONTEND_DIR = REPO_ROOT / "frontend" / "docagent-frontend"
DEFAULT_RUNTIME_DIR = REPO_ROOT / ".runtime"


@dataclass(frozen=True)
class RuntimeLayout:
    repo_root: Path = REPO_ROOT
    runtime_dir: Path | None = None

    @property
    def root(self) -> Path:
        return self.runtime_dir or self.repo_root / ".runtime"

    @property
    def pid_dir(self) -> Path:
        return self.root / "pids"

    @property
    def log_root(self) -> Path:
        return self.repo_root / "logs"

    def pid_file(self, service_name: str) -> Path:
        return self.pid_dir / f"{service_name}.pid"

    def log_dir(self, service_name: str) -> Path:
        return self.log_root / service_name

    def log_file(self, service_name: str) -> Path:
        return self.log_dir(service_name) / "current.log"

    def ensure(self) -> None:
        self.pid_dir.mkdir(parents=True, exist_ok=True)
        self.log_root.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class ServiceSpec:
    name: str
    command: list[str]
    cwd: Path
    port: int
    health_url: str
    env: dict[str, str] = field(default_factory=dict)
    startup_timeout: int = 90


def backend_python() -> Path:
    return Path(os.getenv("DOCAGENT_BACKEND_PYTHON", str(BACKEND_DIR / ".venv" / "bin" / "python")))


def frontend_port() -> int:
    return int(os.getenv("DOCAGENT_FRONTEND_PORT", "3000"))


def backend_port() -> int:
    return int(os.getenv("DOCAGENT_PORT", os.getenv("UVICORN_PORT", "6008")))


def local_embedding_port() -> int:
    return int(os.getenv("LOCAL_EMBEDDING_PORT", "8011"))


def lightrag_port() -> int:
    base_url = os.getenv("LIGHTRAG_BASE_URL", "http://127.0.0.1:9621")
    return int(base_url.rsplit(":", 1)[-1].split("/", 1)[0])


def lightrag_service_env() -> dict[str, str]:
    return build_lightrag_env(
        root_dir=REPO_ROOT,
        doubao_api_key=DOUBAO_API_KEY,
        doubao_llm_api_url=DOUBAO_LLM_API_URL,
        doubao_llm_model=DOUBAO_DEFAULT_LLM_MODEL,
        embedding_host=f"http://127.0.0.1:{local_embedding_port()}/v1",
        embedding_model=LOCAL_EMBEDDING_MODEL_NAME,
        embedding_dim=LOCAL_EMBEDDING_DIM,
    )


def service_specs() -> dict[str, ServiceSpec]:
    python = str(backend_python())
    api_port = backend_port()
    embedding_port = local_embedding_port()
    rag_port = lightrag_port()
    vite_port = frontend_port()

    return {
        "local_embedding": ServiceSpec(
            name="local_embedding",
            command=[python, "local_embedding_server.py"],
            cwd=BACKEND_DIR,
            port=embedding_port,
            health_url=f"http://127.0.0.1:{embedding_port}/health",
            startup_timeout=int(os.getenv("LOCAL_EMBEDDING_STARTUP_TIMEOUT_SECONDS", "45")),
        ),
        "lightrag": ServiceSpec(
            name="lightrag",
            command=[python, "scripts/run_lightrag_server.py"],
            cwd=BACKEND_DIR,
            port=rag_port,
            health_url=f"http://127.0.0.1:{rag_port}/health",
            env=lightrag_service_env(),
            startup_timeout=int(os.getenv("LIGHTRAG_STARTUP_TIMEOUT_SECONDS", "90")),
        ),
        "api": ServiceSpec(
            name="api",
            command=[python, "main.py"],
            cwd=BACKEND_DIR,
            port=api_port,
            health_url=f"http://127.0.0.1:{api_port}/health",
            env={
                "LOCAL_EMBEDDING_AUTO_START": "false",
                "LIGHTRAG_AUTO_START": "false",
                "DOCAGENT_SERVE_FRONTEND_DIST": "false",
                "UVICORN_PORT": str(api_port),
                "UVICORN_WORKERS": os.getenv("UVICORN_WORKERS", "1"),
            },
            startup_timeout=int(os.getenv("DOCAGENT_API_STARTUP_TIMEOUT_SECONDS", "90")),
        ),
        "frontend": ServiceSpec(
            name="frontend",
            command=["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", str(vite_port)],
            cwd=FRONTEND_DIR,
            port=vite_port,
            health_url=f"http://127.0.0.1:{vite_port}/",
            startup_timeout=int(os.getenv("DOCAGENT_FRONTEND_STARTUP_TIMEOUT_SECONDS", "60")),
        ),
    }


def expand_target(target: str) -> list[ServiceSpec]:
    specs = service_specs()
    if target in ("backend", "default"):
        return [specs["local_embedding"], specs["lightrag"], specs["api"]]
    if target == "all":
        return [specs["local_embedding"], specs["lightrag"], specs["api"], specs["frontend"]]
    if target == "frontend":
        return [specs["frontend"]]
    if target in specs:
        return [specs[target]]
    raise ValueError(f"unknown target: {target}")


def cleanup_logs(log_dir: Path, *, retention_days: int, max_bytes: int, now: float | None = None) -> None:
    if not log_dir.exists():
        return
    current_time = time.time() if now is None else now
    cutoff = current_time - retention_days * 24 * 60 * 60
    log_files = sorted(
        (path for path in log_dir.glob("*.log") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
    )
    for path in list(log_files):
        if path.stat().st_mtime < cutoff:
            path.unlink(missing_ok=True)
    log_files = sorted(
        (path for path in log_dir.glob("*.log") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
    )
    total_size = sum(path.stat().st_size for path in log_files)
    for path in log_files:
        if total_size <= max_bytes:
            break
        if path.name == "current.log" and len(log_files) == 1:
            break
        total_size -= path.stat().st_size
        path.unlink(missing_ok=True)


def rotate_current_log(log_file: Path) -> None:
    if not log_file.exists() or log_file.stat().st_size == 0:
        return
    rotated = log_file.with_name(time.strftime("%Y%m%d-%H%M%S.log"))
    log_file.rename(rotated)


def cleanup_all_logs(layout: RuntimeLayout, services: Iterable[ServiceSpec]) -> None:
    retention_days = int(os.getenv("DOCAGENT_LOG_RETENTION_DAYS", "7"))
    max_mb = int(os.getenv("DOCAGENT_LOG_MAX_MB_PER_SERVICE", "100"))
    max_bytes = max_mb * 1024 * 1024
    for service in services:
        cleanup_logs(layout.log_dir(service.name), retention_days=retention_days, max_bytes=max_bytes)


def read_pid(pid_file: Path) -> int | None:
    try:
        return int(pid_file.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return None


def is_process_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    proc_status = Path(f"/proc/{pid}/status")
    if proc_status.exists():
        try:
            status_text = proc_status.read_text(encoding="utf-8")
        except OSError:
            return True
        for line in status_text.splitlines():
            if line.startswith("State:"):
                return not line.split(":", 1)[1].strip().startswith("Z")
    return True


def port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def health_ok(url: str, timeout: float = 2.0) -> bool:
    request = Request(url, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            if not (200 <= response.status < 400):
                return False
            try:
                payload = json.loads(response.read().decode("utf-8"))
            except Exception:
                return True
            if isinstance(payload, dict) and "status" in payload:
                return str(payload.get("status") or "").lower() == "healthy"
            return True
    except (OSError, URLError):
        return False


def wait_for_health(service: ServiceSpec) -> bool:
    deadline = time.monotonic() + service.startup_timeout
    while time.monotonic() < deadline:
        if health_ok(service.health_url):
            return True
        time.sleep(1)
    return False


def preflight(target: str, runtime_dir: str | None = None) -> int:
    services = expand_target(target)
    python = backend_python()
    resolved_runtime_dir = runtime_dir or os.getenv("DOCAGENT_RUNTIME_DIR")
    layout = RuntimeLayout(runtime_dir=Path(resolved_runtime_dir) if resolved_runtime_dir else None)
    failures: list[str] = []
    if not python.exists():
        failures.append(f"missing backend python: {python}")
    if target in ("all", "frontend") and not (FRONTEND_DIR / "node_modules").exists():
        failures.append(f"missing frontend dependencies: {FRONTEND_DIR / 'node_modules'}")
    if not (BACKEND_DIR / "secrets_api.py").exists() and not os.getenv("DOUBAO_API_KEY"):
        failures.append("missing backend/secrets_api.py and DOUBAO_API_KEY env")
    if target in ("all", "frontend") and shutil.which("npm") is None:
        failures.append("missing npm executable")
    for service in services:
        if port_open(service.port):
            pid = read_pid(layout.pid_file(service.name))
            if not (pid and is_process_running(pid)):
                failures.append(f"port {service.port} is already in use for {service.name}")
    if failures:
        for failure in failures:
            print(f"[docagent] preflight failed: {failure}", file=sys.stderr)
        return 1
    print("[docagent] preflight ok")
    return 0


def start_service(service: ServiceSpec, layout: RuntimeLayout, *, force: bool = False) -> int:
    layout.ensure()
    pid_file = layout.pid_file(service.name)
    existing_pid = read_pid(pid_file)
    if existing_pid and is_process_running(existing_pid):
        print(f"[docagent] {service.name} already running pid={existing_pid}")
        return 0
    if existing_pid:
        pid_file.unlink(missing_ok=True)

    if port_open(service.port):
        message = f"[docagent] port {service.port} is already in use for {service.name}"
        if not force:
            print(f"{message}; use --force to stop project pid if recorded", file=sys.stderr)
            return 1
        print(message, file=sys.stderr)

    log_dir = layout.log_dir(service.name)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = layout.log_file(service.name)
    rotate_current_log(log_file)
    cleanup_logs(
        log_dir,
        retention_days=int(os.getenv("DOCAGENT_LOG_RETENTION_DAYS", "7")),
        max_bytes=int(os.getenv("DOCAGENT_LOG_MAX_MB_PER_SERVICE", "100")) * 1024 * 1024,
    )
    env = dict(os.environ)
    env.update(service.env)
    env["PYTHONUNBUFFERED"] = "1"
    with log_file.open("a", encoding="utf-8") as handle:
        process = subprocess.Popen(
            service.command,
            cwd=str(service.cwd),
            env=env,
            stdout=handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    pid_file.write_text(str(process.pid), encoding="utf-8")
    print(f"[docagent] started {service.name} pid={process.pid} log={log_file}")
    if wait_for_health(service):
        print(f"[docagent] {service.name} healthy: {service.health_url}")
        return 0
    print(f"[docagent] {service.name} did not become healthy: {service.health_url}", file=sys.stderr)
    tail_log(service.name, layout, lines=80)
    return 1


def stop_service(service: ServiceSpec, layout: RuntimeLayout) -> int:
    pid_file = layout.pid_file(service.name)
    pid = read_pid(pid_file)
    if not pid:
        print(f"[docagent] {service.name} not managed")
        return 0
    if not is_process_running(pid):
        pid_file.unlink(missing_ok=True)
        print(f"[docagent] {service.name} stale pid removed")
        return 0
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        pid_file.unlink(missing_ok=True)
        return 0
    except PermissionError:
        os.kill(pid, signal.SIGTERM)

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if not is_process_running(pid):
            break
        time.sleep(0.2)
    if is_process_running(pid):
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except PermissionError:
            os.kill(pid, signal.SIGKILL)
    pid_file.unlink(missing_ok=True)
    print(f"[docagent] stopped {service.name} pid={pid}")
    return 0


def status_service(service: ServiceSpec, layout: RuntimeLayout) -> int:
    pid = read_pid(layout.pid_file(service.name))
    managed = bool(pid and is_process_running(pid))
    healthy = health_ok(service.health_url)
    state = "healthy" if healthy else "unhealthy"
    process_state = f"pid={pid}" if managed else "not-managed"
    print(f"{service.name}: {process_state} port={service.port} {state} {service.health_url}")
    return 0 if healthy else 1


def tail_log(service_name: str, layout: RuntimeLayout, *, lines: int = 120) -> int:
    log_file = layout.log_file(service_name)
    if not log_file.exists():
        print(f"[docagent] no log file for {service_name}: {log_file}", file=sys.stderr)
        return 1
    content = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    print("\n".join(content[-lines:]))
    return 0


def command_start(args: argparse.Namespace) -> int:
    target = args.target or "backend"
    services = expand_target(target)
    layout = RuntimeLayout(runtime_dir=Path(args.runtime_dir) if args.runtime_dir else None)
    cleanup_all_logs(layout, services)
    if not args.skip_preflight:
        result = preflight(target, args.runtime_dir)
        if result != 0:
            return result
    for service in services:
        result = start_service(service, layout, force=args.force)
        if result != 0:
            return result
    return 0


def command_stop(args: argparse.Namespace) -> int:
    target = args.target or "all"
    services = list(reversed(expand_target(target)))
    layout = RuntimeLayout(runtime_dir=Path(args.runtime_dir) if args.runtime_dir else None)
    result = 0
    for service in services:
        result = max(result, stop_service(service, layout))
    return result


def command_status(args: argparse.Namespace) -> int:
    target = args.target or "all"
    services = expand_target(target)
    layout = RuntimeLayout(runtime_dir=Path(args.runtime_dir) if args.runtime_dir else None)
    result = 0
    for service in services:
        result = max(result, status_service(service, layout))
    return result


def command_restart(args: argparse.Namespace) -> int:
    stop_args = argparse.Namespace(target=args.target, runtime_dir=args.runtime_dir)
    start_args = argparse.Namespace(
        target=args.target,
        runtime_dir=args.runtime_dir,
        force=args.force,
        skip_preflight=args.skip_preflight,
    )
    stop_result = command_stop(stop_args)
    start_result = command_start(start_args)
    return max(stop_result, start_result)


def command_logs(args: argparse.Namespace) -> int:
    layout = RuntimeLayout(runtime_dir=Path(args.runtime_dir) if args.runtime_dir else None)
    return tail_log(args.service, layout, lines=args.lines)


def command_doctor(args: argparse.Namespace) -> int:
    return preflight(args.target or "all", args.runtime_dir)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DocAgentRAG local development supervisor")
    parser.add_argument("--runtime-dir", default=os.getenv("DOCAGENT_RUNTIME_DIR"))
    subparsers = parser.add_subparsers(dest="command", required=True)

    start_parser = subparsers.add_parser("start")
    start_parser.add_argument("target", nargs="?", default="backend")
    start_parser.add_argument("--force", action="store_true")
    start_parser.add_argument("--skip-preflight", action="store_true")
    start_parser.set_defaults(func=command_start)

    stop_parser = subparsers.add_parser("stop")
    stop_parser.add_argument("target", nargs="?", default="all")
    stop_parser.set_defaults(func=command_stop)

    restart_parser = subparsers.add_parser("restart")
    restart_parser.add_argument("target", nargs="?", default="backend")
    restart_parser.add_argument("--force", action="store_true")
    restart_parser.add_argument("--skip-preflight", action="store_true")
    restart_parser.set_defaults(func=command_restart)

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("target", nargs="?", default="all")
    status_parser.set_defaults(func=command_status)

    logs_parser = subparsers.add_parser("logs")
    logs_parser.add_argument("service")
    logs_parser.add_argument("--lines", type=int, default=120)
    logs_parser.set_defaults(func=command_logs)

    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("target", nargs="?", default="all")
    doctor_parser.set_defaults(func=command_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        print(f"[docagent] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
