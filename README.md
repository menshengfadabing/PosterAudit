# 品牌合规审核后端（check_2）

`check_2` 是品牌设计稿审核系统的后端服务，当前仅保留 Web/API 架构（已移除桌面 GUI）。

## 1. 技术栈
- FastAPI + SQLModel
- PostgreSQL（业务数据）
- Redis（Celery Broker/Result + 任务状态缓存）
- Celery（异步审核队列）
- Uvicorn（API 服务）

## 2. 目录结构
- `web/`：API 入口与路由
  - `web/main.py`：FastAPI 应用入口
  - `web/routers/`：`brands`、`audit`、`review`、`stats`
  - `web/tasks/`：Celery 任务（`audit.run`）
- `src/`：核心业务服务与配置
  - `src/services/`：规则解析、审核编排、LLM 调用
  - `src/utils/config.py`：统一配置（含 LLM/MLLM、鉴权、隔离、Redis/Celery）
- `scripts/`：服务启停脚本（`backendctl.sh`）
- `test/perf/`：性能测试脚本（Locust + pytest）
- `docs/`：升级方案与性能测试文档

## 3. 关键能力
- 品牌规则管理与版本化（管理员接口）
- 审核任务提交、状态轮询、历史查询
- 人工复核流程（待复核/已复核）
- 用户级数据隔离（可配置）与管理员权限控制
- Celery 异步队列执行与失败重试（`audit.run` 最大重试 2 次）

## 4. 环境变量（当前命名）
请使用 `.env`（参考 `.env.example`）：

- 文本模型（规则解析）
  - `LLM_API_KEY`
  - `LLM_API_BASE`
  - `LLM_MODEL`
- 多模态模型（图片审核）
  - `MLLM_API_KEY` 或 `MLLM_API_KEYS`
  - `MLLM_API_KEY_0`, `MLLM_API_KEY_1`, ...（推荐，多 Key 轮询）
  - `MLLM_API_BASE`
  - `MLLM_MODEL`
- 基础设施
  - `DATABASE_URL`
  - `REDIS_URL` / `REDIS_RESULT_URL` / `REDIS_CACHE_URL`
  - `USE_CELERY=true|false`
- 权限与隔离
  - `ENABLE_JAVA_AUTH`
  - `JAVA_USERINFO_URL`
  - `ENABLE_USER_ISOLATION`

## 5. 快速启动（推荐）
### 5.1 安装依赖
```bash
uv sync
```

### 5.2 一键启动后端（API + Celery）
```bash
./scripts/backendctl.sh up
```

### 5.3 查看状态/日志/停止
```bash
./scripts/backendctl.sh status
./scripts/backendctl.sh logs api
./scripts/backendctl.sh logs celery 1
./scripts/backendctl.sh down

# 若 docker compose down 提示网络仍占用，可执行强制清理
./scripts/docker-down-force.sh
```

### 5.4 可选参数
```bash
CELERY_WORKERS=3 CELERY_CONCURRENCY=8 API_PORT=18080 ./scripts/backendctl.sh up
```

## 6. 手动启动（备选）
```bash
uv run uvicorn web.main:app --host 0.0.0.0 --port 18080 --reload
uv run celery -A celery_app.celery worker -Q audit -l info --concurrency=8 -n audit1@%h
```

健康检查：
```bash
curl http://localhost:18080/health
```

## 7. 常用接口（`/api/v1`）
- 品牌：`/brands`、`/brands/{id}`、`/brands/{id}/checklist`
- 审核：`POST /audit`、`GET /tasks/{task_id}`、`GET /history`
- 复核：`/review/tasks`、`/review/tasks/{task_id}`
- 统计：`/queue/status`、`/history/stats`、`/reviewers`

## 8. 联调说明
前端仓库 `design-portal-front` 通过 `/audit-api` 代理到本服务（默认 `http://localhost:18080`）。

## 9. 性能测试
- 脚本：`test/perf/locustfile.py`、`test/perf/test_consistency.py`
- 方案文档：`docs/系统性能测试.md`
- 最新报告：`docs/性能测试报告.md`

## 10. 排障建议
- 若任务长期 `pending/running`：优先检查 Celery worker 是否在线、任务名是否注册（`audit.run`）。
- 若接口 403：检查当前用户身份头、管理员权限和 `ENABLE_USER_ISOLATION` 配置。
- 若审核结果为空：优先检查 `MLLM_API_KEY_*` 是否正确加载（避免旧环境变量干扰）。
