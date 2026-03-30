# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Brand Compliance Audit Platform (品牌合规性智能审核平台) - A PySide6 desktop application that uses LLM to audit design materials against brand guidelines. Uses DeepSeek for document parsing and Doubao (multimodal) for image analysis.

**Note**: `pyproject.toml` requires Python >= 3.12, but GitHub Actions uses Python 3.11 for cross-platform builds. Local development should use 3.12+.

## Common Commands

```bash
# Install dependencies
uv sync

# Run application
uv run python main.py

# Run core module tests (imports, services, schemas, cache)
uv run python test/test_core.py

# Run full flow test (document parsing + image audit + report generation)
# Requires test data in data/uploads/
uv run python test/test_full_flow.py

# Test DeepSeek API connectivity
uv run python test/test_deepseek.py

# Package executable locally
pyinstaller build.spec

# Release: Push a version tag to trigger GitHub Actions cross-platform build
git tag v1.0.0 && git push --tags
```

## Architecture

### Layer Structure

```
main.py                 # Application entry point, Qt setup, font detection
├── gui/                # PySide6 UI layer
│   ├── main_window.py  # QMainWindow with sidebar navigation
│   ├── pages/          # Feature pages (settings_page, audit_page, history_page, rules_page)
│   ├── widgets/        # Reusable components (image_drop_area, progress_panel, streaming_text_display)
│   └── utils/worker.py # QThread background task runner
│
└── src/                # Business logic layer
    ├── models/schemas.py    # Pydantic data models
    ├── services/            # Core services (all singletons, exported via __init__.py)
    └── utils/config.py      # Pydantic-settings configuration
```

### Key Services (Singletons)

All services are singleton instances exported from `src/services/__init__.py`:

- **llm_service** (`LLMService`): LangChain + OpenAI-compatible API for image audit
  - Key methods: `audit_image()`, `audit_image_stream()`, `audit_images_batch()`, `audit_images_batch_stream()`, `calculate_max_images()`, `test_doubao_connection()`, `test_deepseek_connection()`
  - Built-in token estimation for context window management
  - Uses `COMPRESSED_AUDIT_PROMPT` (single image) and `BATCH_AUDIT_PROMPT` (multi-image)
  - Stream methods yield text chunks; use `parse_stream_result()` to parse complete JSON

- **audit_service** (`AuditService`): Image preprocessing and audit orchestration
  - Key methods: `audit()`, `audit_file()`, `batch_audit_concurrent()`, `batch_audit_merged()`
  - Handles image compression with presets: `high_quality`, `balanced`, `high_compression`, `no_compression`
  - `preprocess_image()` compresses/resizes images before API calls

- **document_parser** (`DocumentParser`): Extracts text from documents, uses LLM to parse into BrandRules
  - Supports: PDF, PPT, PPTX, DOC, DOCX, XLS, XLSX, MD, TXT
  - Key methods: `parse()`, `parse_file()`, `extract_text_only()`, `_extract_rules_with_llm()`, `_extract_rules_with_llm_stream()`
  - Uses DeepSeek API for text-based rule extraction

- **rules_context** (`RulesContextManager`): Manages brand rules cache and persistence in `data/rules/`
  - Key methods: `get_rules()`, `add_rules()`, `get_rules_checklist()`, `get_rules_text()`, `set_current_brand()`
  - Persists rules to `data/rules/{brand_id}/current.json`

### Dual-Model Architecture

1. **DeepSeek** (text-only): Parses brand guideline documents into structured rules
   - Config: `deepseek_api_key`, `deepseek_api_base`, `deepseek_model`
   - Used by `document_parser._extract_rules_with_llm()`

2. **Doubao** (multimodal): Audits images against brand rules
   - Config: `openai_api_key`, `openai_api_base`, `doubao_model`
   - Used by `llm_service.audit_image()` and `llm_service.audit_images_batch()`

### Batch Audit Modes

Two approaches for batch processing in `AuditService`:

1. **`batch_audit_concurrent()`**: Multiple parallel API calls (default `max_concurrent=5`)
   - Each image gets its own API request
   - Uses `ThreadPoolExecutor` for concurrency
   - Supports `result_callback` for streaming results

2. **`batch_audit_merged()`**: Single merged request with multiple images
   - Auto-calculates `max_images_per_request` based on token limits
   - Falls back to single-image audit if batch fails
   - More efficient for small batches with good token management
   - Max images capped at 10 per request (safety limit)

### Token Estimation

`LLMService.calculate_max_images()` dynamically computes batch size based on:
1. **Input context window** (128k default): system prompt + rules + image tiles
2. **Output token limit** (8k default, configurable to 16k): each image ~2000 tokens output
   - Output limit is often the real bottleneck for batch processing
3. **Image tile calculation**: 85 base tokens + 170 per 512×512 tile

Use this when planning batch operations to avoid truncation errors.

### Data Flow

1. **Upload brand guidelines** → DocumentParser extracts text → DeepSeek parses into BrandRules → RulesContextManager stores in `data/rules/{brand_id}/current.json`
2. **Audit image** → AuditService preprocesses (compress/resize) → Doubao API call with rules checklist → AuditReport returned

### Streaming Implementation

Both document parsing and image audit support real-time streaming:

```python
# Stream audit results
for chunk in llm_service.audit_image_stream(image_base64, format, rules_checklist):
    # Update UI in real-time
    display.append(chunk)

# Parse final JSON after stream completes
result = llm_service.parse_stream_result(full_content)
```

- Uses LangChain's `llm.stream()` for chunk-by-chunk output
- Qt UI updates via `QMetaObject.invokeMethod` for cross-thread safety
- `@Slot` decorators required for Qt slot functions in worker threads

### Rules Checklist System

The `rules_context.get_rules_checklist(brand_id)` generates a structured checklist for LLM prompts:
- Returns list of `{rule_id, content, category, reference}` dicts
- Rule IDs: `Rule_1`, `Rule_2`, etc.
- Categories: Logo规范, 色彩规范, 字体规范, 文案规范, 布局规范, plus any `secondary_rules` categories
- LLM returns `rule_checks` array matching these rule IDs

## Configuration

Environment variables via `.env` file (see `.env.example`):

```env
# Multimodal model (image audit)
OPENAI_API_KEY=your_key
OPENAI_API_BASE=https://ark.cn-beijing.volces.com/api/v3
DOUBAO_MODEL=doubao-seed-2-0-pro-260215

# Text model (document parsing)
DEEPSEEK_API_KEY=your_key
DEEPSEEK_API_BASE=https://ark.cn-beijing.volces.com/api/v3
DEEPSEEK_MODEL=deepseek-v3-2-251201

# Optional proxy
HTTPS_PROXY=socks5://127.0.0.1:1080
```

Data directories auto-created: `data/rules/`, `data/audit_history/`, `data/exports/`, `data/uploads/`

## Key Data Models (src/models/schemas.py)

- **`BrandRules`**: Brand guidelines with `color`, `logo`, `font` (primary) and dynamic `secondary_rules` list
- **`AuditReport`**: Audit result with `score` (0-100), `status`, `detection`, `rule_checks`, `issues`
- **`AuditStatus`**: Enum with 4 values: `pass`, `warning`, `review`, `fail`
- **`RuleCheckItem`**: Individual rule check with `rule_id`, `status` (pass/fail/review), `confidence`, `detail`
- **`SecondaryRule`**: Dynamic rule with `category`, `name`, `content`, `priority`

## GUI Notes

- PySide6-Fluent-Widgets (`qfluentwidgets`) for Windows-style UI with `FluentWindow`
- QThread via `gui/utils/worker.py` for background tasks (avoids blocking UI)
- Sidebar navigation uses `addSubInterface()` and switches `QStackedWidget` pages
- Chinese font auto-detection in `main.py`
- Responsive scaling via `gui/utils/responsive.py`

## Test Structure

- `test/test_core.py`: Module imports, schema validation, service instantiation, rules context CRUD
- `test/test_full_flow.py`: End-to-end document parsing → image audit → report generation
- `test/test_audit.py`: Audit service specific tests
- `test/test_deepseek.py`: DeepSeek API connectivity verification