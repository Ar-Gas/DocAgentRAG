# Repository Guidelines

## Project Structure & Module Organization
`backend/main.py` boots the FastAPI service on port `6008`. API routes live in `backend/api/`, while document parsing, storage, classification, and retrieval logic live in `backend/utils/`. Backend tests are under `backend/test/`, with fixture files in `backend/test/test_date/`.

The Vue app lives in `frontend/docagent-frontend/`. Keep page-level code in `src/views/`, reusable UI in `src/components/`, shared HTTP calls in `src/api/index.js`, and styles in `src/assets/styles/`. Runtime data in `backend/data/`, `backend/doc/`, `backend/chromadb/`, and `backend/models/` is local state, not source.

## Build, Test, and Development Commands
- `cd backend && pip install -r requirements.txt`: install backend dependencies.
- `cd backend && python main.py`: start FastAPI + Uvicorn locally at `http://localhost:6008`.
- `cd backend && python -m pytest test`: run backend tests.
- `cd frontend/docagent-frontend && npm install`: install frontend dependencies.
- `cd frontend/docagent-frontend && npm run dev`: start the Vite dev server at `http://localhost:3000`.
- `cd frontend/docagent-frontend && npm run build`: create the production bundle.

## Coding Style & Naming Conventions
Use 4-space indentation in Python and follow the existing split between thin API layers and heavier utility modules. Prefer `snake_case` for Python files, functions, and variables, and `PascalCase` for classes.

Frontend code uses 2-space indentation, Vue 3 `script setup`, `PascalCase` component filenames such as `FileUpload.vue`, and `camelCase` for JavaScript helpers and API methods. `black` and `flake8` are available for backend formatting and linting; no repo-level frontend linter is configured.

## Testing Guidelines
Backend tests follow `test_*.py` naming and are written in `unittest` style while being executed with `pytest`. Add tests next to the affected backend area and reuse files from `backend/test/test_date/` when changing document parsing. No coverage gate is configured, so contributors should add targeted regression tests for storage, retrieval, and parsing changes.

## Commit & Pull Request Guidelines
Git history uses short, specific subject lines, often in Chinese or simple English, for example `补充vite.config.js` or `Update README.md`. Keep commits focused and describe the changed area directly.

Pull requests should summarize behavior changes, mention any required config or model updates, and include test evidence. Attach screenshots for frontend UI changes and link related issues when applicable.

## Security & Configuration Tips
Keep secrets in `backend/api_secrets.py` or environment variables. Do not commit generated content from `backend/data/`, `backend/doc/`, `backend/chromadb/`, `backend/models/`, `backend/venv/`, or `frontend/docagent-frontend/node_modules/`.
