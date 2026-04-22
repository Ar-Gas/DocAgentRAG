# DocAgentRAG Startup Guide

## Default Runtime Layout

DocAgentRAG runs as independent local services supervised by one command:

- `local_embedding`: `http://127.0.0.1:8011`
- `lightrag`: `http://127.0.0.1:9621`
- `api`: `http://127.0.0.1:6008`
- `frontend`: `http://127.0.0.1:3000`

The default command starts the backend runtime only:

```bash
./start.sh
```

This is equivalent to:

```bash
./start.sh backend
```

It starts, in order:

1. local embedding on `8011`
2. LightRAG on `9621`
3. FastAPI on `6008`

FastAPI is launched with `LOCAL_EMBEDDING_AUTO_START=false` and
`LIGHTRAG_AUTO_START=false` so the three services are separate processes. This
keeps failures isolated and makes logs easier to inspect.

## Common Commands

Start backend runtime:

```bash
./start.sh
```

Start backend runtime and frontend:

```bash
./start.sh all
```

Start only frontend:

```bash
./start.sh frontend
```

Stop all project-managed services:

```bash
./stop.sh
```

Stop backend runtime only:

```bash
./stop.sh backend
```

Check status:

```bash
./status.sh
```

Tail one service log:

```bash
backend/.venv/bin/python backend/scripts/dev_supervisor.py logs api
backend/.venv/bin/python backend/scripts/dev_supervisor.py logs lightrag
backend/.venv/bin/python backend/scripts/dev_supervisor.py logs local_embedding
backend/.venv/bin/python backend/scripts/dev_supervisor.py logs frontend
```

Run environment checks without starting:

```bash
backend/.venv/bin/python backend/scripts/dev_supervisor.py doctor all
```

## Logs And Pids

Pid files are kept under `.runtime/`; service logs are kept under local `logs/`
subdirectories:

```text
.runtime/
  pids/
    api.pid
    frontend.pid
    lightrag.pid
    local_embedding.pid
logs/
  api/current.log
  frontend/current.log
  lightrag/current.log
  local_embedding/current.log
```

On each start, an existing `current.log` is rotated to a timestamped log in the
same service directory.

Log cleanup runs automatically on startup:

- default retention: `7` days
- default max size: `100` MB per service

Override when needed:

```bash
DOCAGENT_LOG_RETENTION_DAYS=3 ./start.sh all
DOCAGENT_LOG_MAX_MB_PER_SERVICE=50 ./start.sh all
DOCAGENT_RUNTIME_DIR=/tmp/docagent-runtime ./start.sh
```

## Health Checks

Backend runtime is healthy when all three endpoints respond:

```bash
curl http://127.0.0.1:8011/health
curl http://127.0.0.1:9621/health
curl http://127.0.0.1:6008/health
```

Frontend health:

```bash
curl -I http://127.0.0.1:3000/
```

Useful URLs:

- frontend app: `http://127.0.0.1:3000/`
- backend docs: `http://127.0.0.1:6008/docs`
- backend health: `http://127.0.0.1:6008/health`
- LightRAG WebUI proxy: `http://127.0.0.1:6008/api/v1/admin/lightrag/webui/`

## Configuration

Important environment variables:

- `DOCAGENT_PORT`: FastAPI port, default `6008`
- `DOCAGENT_FRONTEND_PORT`: Vite port, default `3000`
- `LOCAL_EMBEDDING_PORT`: local embedding port, default `8011`
- `LIGHTRAG_BASE_URL`: LightRAG base URL, default `http://127.0.0.1:9621`
- `DOCAGENT_BACKEND_PYTHON`: backend Python executable
- `DOCAGENT_RUNTIME_DIR`: runtime pid/log directory
- `DOCAGENT_LOG_RETENTION_DAYS`: log retention days
- `DOCAGENT_LOG_MAX_MB_PER_SERVICE`: max log MB per service

The one-command supervisor does not kill unrelated processes by default. If a
required port is already occupied by another project, startup fails with a
diagnostic message instead of terminating that process.
