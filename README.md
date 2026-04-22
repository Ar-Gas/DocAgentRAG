# DocAgentRAG

办公文档分类、浏览、检索和 LightRAG 集成系统。

当前推荐运行方式是由 supervisor 统一管理的分离式运行时：

- 前端开发服务：`http://127.0.0.1:3000`（可选）
- 后端 API：`http://127.0.0.1:6008`
- 本地 embedding：`http://127.0.0.1:8011`
- LightRAG：`http://127.0.0.1:9621`

默认一条命令只启动后端运行时：`local_embedding -> lightrag -> api`。
需要联调前端时，再显式启动 `frontend`。

## 快速开始

前置条件：

- `backend/.venv` 已安装后端依赖
- `backend/secrets_api.py` 已配置，或已设置 `DOUBAO_API_KEY`
- 如需启动前端，`frontend/docagent-frontend/node_modules` 已安装前端依赖

推荐命令：

```bash
chmod +x start.sh stop.sh status.sh

# 默认启动后端运行时
./start.sh

# 查看后端运行状态
./status.sh backend

# 停止后端运行时
./stop.sh backend
```

如果需要把前端也一起启动：

```bash
./start.sh all
```

访问地址：

- 前端页面：`http://127.0.0.1:3000`
- 后端接口文档：`http://127.0.0.1:6008/docs`
- 后端健康检查：`http://127.0.0.1:6008/health`
- LightRAG WebUI 代理：`http://127.0.0.1:6008/api/v1/admin/lightrag/webui/`

完整启动说明、日志路径、保留策略和诊断命令见 [STARTUP.md](./STARTUP.md)。

## 当前架构

- `3000`：Vite 前端开发服务，通过代理访问后端 `/api`
- `6008`：FastAPI 后端，只提供 API、健康检查、管理代理
- `8011`：本地 embedding runtime
- `9621`：LightRAG API + WebUI
- `backend/scripts/dev_supervisor.py`：统一负责启动顺序、健康检查、pid 管理、日志轮转和日志清理
- `start.sh` / `stop.sh` / `status.sh`：项目根目录下的稳定入口脚本

在 supervisor 模式下，FastAPI 会带上 `LOCAL_EMBEDDING_AUTO_START=false` 和
`LIGHTRAG_AUTO_START=false` 启动，避免 API 再次托管底层依赖，确保四个服务保持独立进程。

后端默认不再托管前端 `dist`。如确实需要兼容单端口静态托管，可显式设置：

```bash
DOCAGENT_SERVE_FRONTEND_DIST=true
```

## 状态模型

### 入库状态

- `queued`：已进入队列，等待 LightRAG
- `processing`：LightRAG 正在处理
- `ready`：LightRAG 已完成
- `failed`：支持类型的真实失败
- `local_only`：仅本地可浏览，不进入 LightRAG

### 分类状态

- `classification_path` 只保存真实 taxonomy 路径
- `classification_issue_code=no_match` 表示当前 taxonomy 无法可靠命中，需要人工复核
- `classification_issue_code=pending_local_content` 表示本地正文还未准备好

不再使用伪分类路径表达运行状态，例如：

- `待同步 > 待本地索引同步`
- `未分类行政办公 > 未分类 > 待人工确认`

## 开发命令

推荐使用根目录 supervisor 作为日常开发入口：

```bash
./start.sh
./start.sh all
./status.sh
./stop.sh
```

如需单独调试服务，可直接使用底层命令。

后端：

```bash
cd backend
pip install -r requirements.txt
python main.py
python -m pytest test
```

前端：

```bash
cd frontend/docagent-frontend
npm install
npm run dev
npm run build
```

## 备注

- 前端默认通过 Vite 代理访问 `http://localhost:6008`
- 默认日志路径为 `logs/<service>/current.log`
- 默认 pid 路径为 `.runtime/pids/<service>.pid`
- `./start.sh` 可重复执行；已由本项目管理的服务不会因为端口已占用而误报启动失败
- 如浏览器打不开页面，优先执行 `./status.sh` 检查各服务健康状态
- `UVICORN_WORKERS` 本地开发建议保持 `1`
