# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Brand Compliance Audit Platform (品牌合规性智能审核平台) - An LLM-powered platform that audits design materials against brand guidelines. Runs as both a **PySide6 desktop app** and a **FastAPI REST API server**. Uses DeepSeek for document parsing and Doubao (multimodal) for image analysis.

**Note**: `pyproject.toml` requires Python >= 3.12, but GitHub Actions uses Python 3.11 for cross-platform builds. Local development should use 3.12+.

## Common Commands

```bash
# Install dependencies
uv sync

# Run desktop application
uv run python main.py

# Run web API server (FastAPI)
uv run uvicorn web.main:app --host 0.0.0.0 --port 8080 --reload

# Deploy web API with Docker
cd docker && docker-compose -f ../docker-compose.web.yml up -d

# Run core module tests (imports, services, schemas, cache)
uv run python test/test_core.py

# Run full flow test (document parsing + image audit + report generation)
# Requires test data in data/uploads/
uv run python test/test_full_flow.py

# Run audit integration tests with local images
uv run python test/test_audit.py

# Test DeepSeek API connectivity
uv run python test/test_deepseek.py

# Package desktop executable locally
pyinstaller build.spec

# Release: Push a version tag to trigger GitHub Actions cross-platform build
git tag v1.0.0 && git push --tags
```

**Note**: GitHub Actions uses `requirements.txt` with Python 3.11 for cross-platform builds, while local development uses `uv sync` with Python 3.12+. Keep both files in sync when adding dependencies.

## Architecture

### Layer Structure

```
main.py                 # Desktop app entry point, Qt setup, font detection
├── gui/                # PySide6 UI layer
│   ├── main_window.py  # QMainWindow with sidebar navigation
│   ├── pages/          # Feature pages (settings_page, audit_page, history_page, rules_page)
│   ├── widgets/        # Reusable components (image_drop_area, progress_panel, streaming_text_display)
│   └── utils/worker.py # QThread background task runner
│
├── web/                # FastAPI REST API layer
│   ├── main.py         # FastAPI app, CORS, router registration, DB init
│   ├── deps.py         # DB engine (PostgreSQL/psycopg2), session DI, API key auth
│   ├── models/db.py    # SQLModel tables: Brand, AuditTask, ReferenceImage, User, Schedule
│   └── routers/
│       ├── brands.py   # /api/v1/brands — brand CRUD + reference image upload
│       ├── audit.py    # /api/v1/audit, /api/v1/tasks, /api/v1/history
│       ├── review.py   # /api/v1/review — human review queue and decision submission
│       └── stats.py    # /api/v1/queue/status, /api/v1/history/stats
│
└── src/                # Business logic layer (shared by desktop and web)
    ├── models/schemas.py    # Pydantic data models
    ├── services/            # Core services (all singletons, exported via __init__.py)
    └── utils/config.py      # Pydantic-settings configuration
```

### Key Services (Singletons)

All services are singleton instances exported from `src/services/__init__.py`:

- **llm_service** (`LLMService`): LangChain + OpenAI-compatible API for image audit
  - Key methods: `audit_image()`, `audit_image_stream()`, `audit_images_batch_stream()`, `calculate_max_images()`, `test_doubao_connection()`, `test_deepseek_connection()`, `_get_next_api_key()`
  - Built-in token estimation for context window management
  - Uses `COMPRESSED_AUDIT_PROMPT` (single image) and `BATCH_AUDIT_PROMPT` (multi-image)
  - Stream methods yield text chunks; use `parse_stream_result()` to parse complete JSON
  - **Multi-Key support**: `_get_next_api_key()` rotates through configured API keys

- **audit_service** (`AuditService`): Image preprocessing and audit orchestration
  - Key methods: `audit()`, `audit_file()`, `batch_audit_merged()` (primary), `_fallback_concurrent()`
  - Handles image compression with presets: `high_quality`, `balanced`, `high_compression`, `no_compression`
  - `preprocess_image()` compresses/resizes images before API calls
  - **batch_audit_merged**: Combines images per request + ThreadPoolExecutor parallel batches
  - `_is_result_incomplete()`: Detects truncated output, triggers auto-retry

- **document_parser** (`DocumentParser`): Extracts text from documents, uses LLM to parse into BrandRules
  - Supports: PDF, PPT, PPTX, DOC, DOCX, XLS, XLSX, MD, TXT
  - Key methods: `parse()`, `parse_file()`, `extract_text_only()`, `_extract_rules_with_llm()`, `_extract_rules_with_llm_stream()` (generator), `parse_stream_result()`
  - Async wrappers: `async_parse()`, `async_extract_rules_with_llm()`, `async_extract_text_only()`
  - Uses DeepSeek API for text-based rule extraction
  - `_extract_rules_with_llm_stream()` yields text chunks; call `parse_stream_result(full_content, filename)` to parse the accumulated stream into `BrandRules`

- **rules_context** (`RulesContextManager`): Manages brand rules cache and persistence in `data/rules/`
  - Key methods: `get_rules()`, `add_rules()`, `get_rules_checklist()`, `get_rules_text()`, `set_current_brand()`
  - `get_rules_checklist(brand_id, preconditions)`: Only uses `secondary_rules` (not primary color/logo/font structures). Accepts optional `preconditions` dict to filter/exempt rules via `_apply_preconditions()`
  - Persists rules to `data/rules/{brand_id}/current.json`
  - Async wrappers: `async_reparse_rules_from_raw_text(brand_id)`

### Dual-Model Architecture

1. **DeepSeek** (text-only): Parses brand guideline documents into structured rules
   - Config: `deepseek_api_key`, `deepseek_api_base`, `deepseek_model`
   - Used by `document_parser._extract_rules_with_llm()`

2. **Doubao** (multimodal): Audits images against brand rules
   - Config: `openai_api_key` (single) or `openai_api_keys` (comma-separated) or `OPENAI_API_KEY_0/1/2...` (indexed)
   - The `OPENAI_API_BASE` and `DOUBAO_MODEL` point to any OpenAI-compatible multimodal API (Doubao, Kimi, Qwen, etc.)
   - **Multi-Key rotation**: `settings.get_openai_api_keys()` returns list; `_get_next_api_key()` cycles through

### Batch Audit Strategy (Merge + Parallel)

`batch_audit_merged()` is the primary batch processing method, combining two strategies:

1. **Merge**: Single API call processes multiple images (batch size configurable in GUI: 3/5/8/10 or auto)
2. **Parallel**: ThreadPoolExecutor runs multiple batches concurrently
   - Each batch uses different API Key (round-robin rotation)
   - Concurrent workers = min(batch_count, key_count)

Flow:
```
9 images → 3 batches (3 each) → parallel execution
Batch 1 → Key #1 → single API call for 3 images
Batch 2 → Key #2 → single API call for 3 images  } concurrent
Batch 3 → Key #3 → single API call for 3 images
```

Fallback: If merged request fails (or >50% of rules missing from output per `_is_result_incomplete()`), `_fallback_concurrent()` processes images individually with a different API key.

**Simplified Output Format**: LLM returns `{"id": "Rule_N", "s": "p|f|r", "c": 0.0-1.0}` instead of full `status/confidence/detail`, saving ~70% tokens. `OUTPUT_TOKENS_PER_IMAGE = 500`.

### Web REST API Layer

The `web/` package is a FastAPI application that exposes the same core services over HTTP. It requires a **PostgreSQL** database (configured via `DATABASE_URL` env var, defaults to `postgresql+psycopg2://postgres:postgres123456@localhost:5432/app`).

**Authentication**: All routes require `X-API-Key` header. Set `ALLOWED_API_KEYS` env var (comma-separated) to enable; omitting it disables auth entirely.

**Key API Endpoints** (`/api/v1`):

| Method | Path | Description |
|--------|------|-------------|
| POST | `/brands` | Upload single doc → parse → create brand |
| POST | `/brands/merge` | Upload multiple docs → merge → create brand |
| GET | `/brands` | List all brands |
| GET/PUT/DELETE | `/brands/{brand_id}` | Get/update/delete brand; `action=reparse` re-runs LLM on stored raw_text |
| POST | `/brands/{brand_id}/images` | Upload reference images (Logo standard assets) |
| DELETE | `/brands/{brand_id}/images/{filename}` | Delete reference image |
| POST | `/audit` | Submit audit task (`mode=async` returns task_id, `mode=sync` waits) |
| GET | `/tasks/{task_id}` | Poll task status and results |
| DELETE | `/tasks/{task_id}` | Delete audit history record |
| GET | `/history` | List audit history with pagination and brand filter |
| GET | `/review/tasks` | List tasks in human review queue (filter by `pending_review`/`completed_review`) |
| GET | `/review/tasks/{task_id}` | Get single review task detail |
| GET | `/review/tasks/{task_id}/image` | Get image stream for a review task |
| POST | `/review/tasks/{task_id}/decision` | Submit human review decision (`passed`/`failed`) |
| GET | `/queue/status` | Get current review queue status and reviewer availability |
| GET | `/history/stats` | Get historical stats (last N days, by status/result/brand) |

**DB Models** (`web/models/db.py`): `Brand`, `AuditTask` (status: pending/running/completed/failed/pending_review), `ReferenceImage`, `User` (role: user/reviewer/admin), `Schedule` (daily reviewer assignments). Tables auto-created on startup via `SQLModel.metadata.create_all()`.

**Human Review Flow**: After machine audit completes, tasks with `machine_result=manual_review` can be set to `pending_review` status. Reviewers use `/review/tasks` to list and `/review/tasks/{id}/decision` to submit `passed`/`failed`. `AuditTask` stores `reviewer_id`, `review_result`, `review_comment`, `review_at`.

**Async audit flow**: `POST /audit` saves files to `data/uploads/{task_id}/`, writes `AuditTask` as `pending`, then runs `audit_service.batch_audit_merged()` in a thread pool via `loop.run_in_executor()`. The `preconditions` form field (JSON string) is parsed and passed to `rules_context.get_rules_checklist()` for rule exemption/filtering.

### Data Flow

1. **Upload brand guidelines** → DocumentParser extracts text → DeepSeek parses into BrandRules → RulesContextManager stores in `data/rules/{brand_id}/current.json`
2. **Audit image** → AuditService preprocesses (compress/resize) → Doubao API call with rules checklist → AuditReport returned

### Token Estimation

`LLMService.calculate_max_images()` dynamically computes batch size based on:
1. **Input context window** (128k default): system prompt + rules + image tiles
2. **Output token limit** (8k default): each image ~500 tokens output (simplified format)
3. **Image tile calculation**: 85 base tokens + 170 per 512×512 tile

### Streaming Implementation

Both document parsing and image audit support real-time streaming:

```python
# Stream audit results
for chunk in llm_service.audit_image_stream(image_base64, format, rules_checklist):
    display.append(chunk)

# Parse final JSON after stream completes
result = llm_service.parse_stream_result(full_content)
```

- Uses LangChain's `llm.stream()` for chunk-by-chunk output
- Qt UI updates via `QMetaObject.invokeMethod` for cross-thread safety
- `@Slot` decorators required for Qt slot functions in worker threads

### Rules Checklist System

The `rules_context.get_rules_checklist(brand_id, preconditions)` generates a structured checklist for LLM prompts:
- Returns list of `{rule_id, content, category, reference}` dicts, plus optional structured fields: `rule_source_id`, `fail_condition`, `review_condition`, `pass_condition`
- **Only uses `secondary_rules`** — primary color/logo/font structures are NOT included to avoid duplicate rules
- Rule IDs: `Rule_1`, `Rule_2`, etc.
- `llm_service._format_checklist()` formats rules with `[级别:XXX]` tags when `output_level` is present (legacy field)

**Preconditions System**: `get_rules_checklist()` accepts a `preconditions` dict, which `_apply_preconditions()` uses to:
1. **Exempt rules**: Skip rules whose `rule_source_id` matches exemption sets based on `brand_status`, `joint_brand`, `collab_lead`
   - `brand_status=none` → skip all Logo rules
   - `brand_status=main_subject` → skip Logo position/size rules (H-LOGO-05, H-LOGO-06)
   - `joint_brand=none` → skip joint-brand rules (H-LOGO-08, H-LOGO-10)
   - `collab_lead=partner` → skip Logo position/size rules
2. **Inject context**: Append `[前置条件]` tags to relevant rules with `comm_type`, `material_type`, `channels`, etc.
3. Re-number `rule_id` sequentially after filtering

**Reparse utility**: `rules_context.reparse_rules_from_raw_text(brand_id)` re-runs DeepSeek parsing on stored `raw_text`.

## Configuration

Environment variables via `.env` file (see `.env.example`):

```env
# Multimodal model (image audit) - Multi-Key supported
OPENAI_API_KEY_0=your_key_1
OPENAI_API_KEY_1=your_key_2
OPENAI_API_BASE=https://ark.cn-beijing.volces.com/api/v3
DOUBAO_MODEL=doubao-seed-2-0-pro-260215

# Text model (document parsing)
DEEPSEEK_API_KEY=your_key
DEEPSEEK_API_BASE=https://ark.cn-beijing.volces.com/api/v3
DEEPSEEK_MODEL=deepseek-v3-2-251201

# Web API only
DATABASE_URL=postgresql+psycopg2://postgres:postgres123456@localhost:5432/app
ALLOWED_API_KEYS=key1,key2  # omit to disable auth

# Optional proxy
HTTPS_PROXY=socks5://127.0.0.1:1080
```

**Multi-API Key priority** (in `settings.get_openai_api_keys()`):
1. `OPENAI_API_KEYS` (comma-separated)
2. `OPENAI_API_KEY_0/1/2...` (indexed format)
3. `OPENAI_API_KEY` (single key fallback)

Data directories auto-created: `data/rules/`, `data/audit_history/`, `data/exports/`, `data/uploads/`

## Key Data Models (src/models/schemas.py)

- **`BrandRules`**: Brand guidelines with `color`, `logo`, `font` (primary) and dynamic `secondary_rules` list. Also has `preconditions` (list of form-field dicts extracted from brand docs) and `raw_text` (original document text for reparse).
- **`AuditReport`**: Audit result with `score` (0-100, deprecated), `status`, `detection`, `rule_checks`, `issues`
- **`AuditStatus`**: Enum: `pass`, `warning`, `review`, `fail` (UI maps `warning`/`review` to same yellow display)
- **`RuleCheckItem`**: Individual rule check with `rule_id`, `status` (pass/fail/review), `confidence`, `detail`
- **`SecondaryRule`**: Dynamic rule with **three-stage judgment conditions** (new format): `fail_condition`, `review_condition`, `pass_condition` — all `None` by default for backward compatibility. Legacy fields also preserved: `output_level`, `threshold`, `feedback_text`, `rule_source_id`.
  - `fail_condition`: When to mark as FAIL (objective, quantifiable violations)
  - `review_condition`: When to mark as REVIEW (subjective/unconfirmable, needs human review)
  - `pass_condition`: When to mark as PASS (clearly compliant)

## GUI Notes

- PySide6-Fluent-Widgets (`qfluentwidgets`) for Windows-style UI with `FluentWindow`
- QThread via `gui/utils/worker.py` for background tasks
  - `Worker` signals: `started_signal`, `finished_signal(object)`, `error_signal(str)`, `progress_signal(int, str)`
  - Automatically injects `progress_callback` into task kwargs if not already provided
- Chinese font auto-detection in `main.py`
- Responsive scaling via `gui/utils/responsive.py`

## Test Structure

- `test/test_core.py`: Module imports, schema validation, service instantiation, rules context CRUD
- `test/test_full_flow.py`: End-to-end document parsing → image audit → report generation
- `test/test_audit.py`: Integration tests for audit functionality with local images
- `test/test_deepseek.py`: DeepSeek API connectivity verification
- `test/test_fixes.py`: Unit tests for specific fixes (JSON parser, compression, batch audit, model removals)
- `test/test_single_image_raw.py`: Single image raw audit test
- `test/lm_test.py`: LLM service tests

## Prompt Templates

Audit prompts defined in `src/services/llm_service.py`:

- **`COMPRESSED_AUDIT_PROMPT`**: Single image audit - returns JSON with `results` array
- **`BATCH_AUDIT_PROMPT`**: Multi-image audit - returns JSON array with `idx` for each result
- **`REFERENCE_IMAGE_PROMPT`**: Instructions for LLM to compare Logo against reference images

Document parsing prompt defined in `src/services/document_parser.py`:

- **`PARSE_SYSTEM_PROMPT`**: Instructs DeepSeek to extract structured rules from brand documents. Key output format:
  - `preconditions`: Form fields requiring user input before audit (e.g., "品牌标识情况", "传播类型") — stored in `BrandRules.preconditions`, never in `rules`
  - `rules`: All audit rules, each with three-stage judgment conditions:
    - `fail_condition`: Objective, quantifiable FAIL criteria
    - `review_condition`: Subjective/unverifiable situations needing human review
    - `pass_condition`: Clearly compliant criteria
  - `priority`: 1=important (objective), 2=general (subjective), 3=reference

**Simplified Output Format**:
```json
{"id": "Rule_N", "s": "p|f|r", "c": 0.0-1.0}
```
`s`: status (p=pass, f=fail, r=review). `c`: confidence. Results sorted FAIL → REVIEW → PASS.

**Confidence Gating**: `audit_service._build_rule_checks()` demotes low-confidence (<0.5) pass/fail to review.

## Utilities

- **`src/utils/json_parser.py`**: Robust JSON extraction from LLM text. `parse_json_response()` tries direct parse → code block extraction → brace/bracket scanning. Always use these when parsing LLM output.

## 开发规范

每次进行较大代码修改后，按次序完成以下任务：

### 1. 代码审查
对修改的部分进行 code review：删除重复的或无用的代码块，确认代码质量

### 2. 功能测试
在根目录/test/这个文件夹下检查是否存在核心功能测试代码，若存在则运行一次核心功能测试，不存在则编写test_core文件并运行测试

### 3. 更新README.md
更新README.md，记录本次的更改

### 4. 版本管理
使用 git 进行版本管理（commit）。

### 错误修复提示
当用户对某个功能或代码块多次修改仍持续报错时，提醒用户考虑使用 git 回滚到上一个稳定版本，而不是继续在错误的方向上叠加修改。
