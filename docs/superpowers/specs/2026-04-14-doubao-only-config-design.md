# Doubao-Only Config Refactor Design

## Scope

Refactor backend LLM configuration so the project uses Doubao only.

Goals:

- Use `backend/secrets_api.py` as the single code-level configuration source.
- Remove all OpenAI-compatible client branches and `OPENAI_*` settings.
- Default all backend LLM calls to `DOUBAO_MINI_LLM_MODEL`.
- Keep `DOUBAO_LLM_MODEL` defined as a reserved higher-tier model for future use, but do not use it as the default runtime model.
- Update docs and dependencies to match the new design.

Out of scope:

- Frontend UI changes beyond surfacing existing backend status fields.
- Reworking embedding strategy beyond keeping the existing Doubao embedding flow.
- Introducing environment-specific model routing logic.

## Configuration Design

`backend/config.py` becomes the single runtime accessor for backend configuration, but its code-level secret import source changes from `api_secrets` to `secrets_api`.

The config module exposes:

- `DOUBAO_API_KEY`
- `DOUBAO_EMBEDDING_API_URL`
- `DOUBAO_EMBEDDING_MODEL`
- `DOUBAO_LLM_API_URL`
- `DOUBAO_MINI_LLM_MODEL`
- `DOUBAO_LLM_MODEL`
- `DOUBAO_DEFAULT_LLM_MODEL`

`DOUBAO_DEFAULT_LLM_MODEL` is defined as `DOUBAO_MINI_LLM_MODEL` and is the value all runtime LLM callers use unless a future call site explicitly opts into the higher-tier model.

`OPENAI_API_KEY`, `OPENAI_BASE_URL`, and generic `LLM_MODEL` are removed from config and from all callers.

## Runtime Behavior

### Startup

`backend/main.py` treats Doubao API key presence as the only LLM availability signal.

Startup logging changes from a provider switch to a Doubao-only status message that reports whether Doubao is configured and which default model is active.

### Smart Retrieval

`backend/utils/smart_retrieval.py` is simplified to one provider:

- no `openai` import
- no provider fallback logic
- no OpenAI-compatible branch
- all LLM requests go through Doubao HTTP calls

The default chat model used by query expansion, reranking, summarization, and classification-table generation is `DOUBAO_DEFAULT_LLM_MODEL`.

### LLM Classification

`backend/utils/llm_classifier.py` also becomes Doubao-only.

It uses the same default model constant instead of a hard-coded DeepSeek/OpenAI-compatible model string.

## Dependency Changes

`backend/requirements.txt` removes the `openai` package because the runtime no longer imports it.

No new backend dependency is needed because Doubao calls already use `requests`.

## Documentation Changes

Update repository docs so they no longer claim OpenAI-compatible support.

Required doc updates:

- root `README.md`
- any backend-facing setup docs that mention `api_secrets.py` or `OPENAI_*`

Docs should state:

- backend secrets file is `backend/secrets_api.py`
- default LLM path is Doubao
- default chat model is `DOUBAO_MINI_LLM_MODEL`
- `DOUBAO_LLM_MODEL` remains available as a reserved non-default option

## Validation

Implementation is complete when:

1. `rg` finds no remaining imports of `api_secrets` in backend code.
2. `rg` finds no remaining runtime use of `OpenAI`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`, or `LLM_MODEL` in backend code and README.
3. Python backend files compile successfully.
4. Existing frontend static tests still pass in the current environment.

## Risks

- Some test fixtures or archived docs may still mention OpenAI or the old secret filename. Those should be left alone unless they are active setup documentation or runtime code.
- Because the current machine lacks a full backend Python environment, verification will rely on compile checks and targeted static assertions instead of full pytest execution.
