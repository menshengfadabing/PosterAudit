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

# Run audit integration tests with local images
uv run python test/test_audit.py

# Test DeepSeek API connectivity
uv run python test/test_deepseek.py

# Package executable locally
pyinstaller build.spec

# Release: Push a version tag to trigger GitHub Actions cross-platform build
git tag v1.0.0 && git push --tags
```

**Note**: GitHub Actions uses `requirements.txt` with Python 3.11 for cross-platform builds, while local development uses `uv sync` with Python 3.12+. Keep both files in sync when adding dependencies.

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
  - Key methods: `parse()`, `parse_file()`, `extract_text_only()`, `_extract_rules_with_llm()`, `_extract_rules_with_llm_stream()`
  - Uses DeepSeek API for text-based rule extraction

- **rules_context** (`RulesContextManager`): Manages brand rules cache and persistence in `data/rules/`
  - Key methods: `get_rules()`, `add_rules()`, `get_rules_checklist()`, `get_rules_text()`, `set_current_brand()`
  - Persists rules to `data/rules/{brand_id}/current.json`

### Reference Images Feature

Brands can include standard reference images (Logo variants, icons) for visual comparison:
- Stored in `BrandRules.reference_images` as `ReferenceImage` objects
- `llm_service` appends `REFERENCE_IMAGE_PROMPT` when reference images are provided
- LLM compares uploaded design's Logo against reference to detect deformation/color errors

### Dual-Model Architecture

1. **DeepSeek** (text-only): Parses brand guideline documents into structured rules
   - Config: `deepseek_api_key`, `deepseek_api_base`, `deepseek_model`
   - Used by `document_parser._extract_rules_with_llm()`

2. **Doubao** (multimodal): Audits images against brand rules
   - Config: `openai_api_key` (single) or `openai_api_keys` (comma-separated) or `OPENAI_API_KEY_0/1/2...` (indexed)
   - Used by `llm_service.audit_image()` and `llm_service.audit_images_batch_stream()`
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

Fallback: If merged request fails, `_fallback_concurrent()` processes images individually.

**Simplified Output Format**: LLM returns `{"id": "Rule_N", "s": "p|f|r", "c": 0.0-1.0}` instead of full `status/confidence/detail`, saving ~70% tokens.

**Output Token Estimation**: `OUTPUT_TOKENS_PER_IMAGE = 500` (simplified format, down from 2000).

### Token Estimation

`LLMService.calculate_max_images()` dynamically computes batch size based on:
1. **Input context window** (128k default): system prompt + rules + image tiles
2. **Output token limit** (8k default): each image ~500 tokens output (simplified format)
3. **Image tile calculation**: 85 base tokens + 170 per 512×512 tile

With simplified output format, max images per request increased from ~4 to ~16 (output limit 8k / 500 tokens).
GUI allows user override: auto/3/5/8/10 per batch.

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
# Multimodal model (image audit) - Multi-Key supported
OPENAI_API_KEY_0=your_key_1
OPENAI_API_KEY_1=your_key_2
OPENAI_API_KEY_2=your_key_3
OPENAI_API_BASE=https://ark.cn-beijing.volces.com/api/v3
DOUBAO_MODEL=doubao-seed-2-0-pro-260215

# Text model (document parsing)
DEEPSEEK_API_KEY=your_key
DEEPSEEK_API_BASE=https://ark.cn-beijing.volces.com/api/v3
DEEPSEEK_MODEL=deepseek-v3-2-251201

# Optional proxy
HTTPS_PROXY=socks5://127.0.0.1:1080
```

**Multi-API Key priority** (in `settings.get_openai_api_keys()`):
1. `OPENAI_API_KEYS` (comma-separated)
2. `OPENAI_API_KEY_0/1/2...` (indexed format)
3. `OPENAI_API_KEY` (single key fallback)

Data directories auto-created: `data/rules/`, `data/audit_history/`, `data/exports/`, `data/uploads/`

## Key Data Models (src/models/schemas.py)

- **`BrandRules`**: Brand guidelines with `color`, `logo`, `font` (primary) and dynamic `secondary_rules` list
- **`AuditReport`**: Audit result with `score` (0-100), `status`, `detection`, `rule_checks`, `issues`
- **`AuditStatus`**: Enum with 4 values: `pass`, `warning`, `review`, `fail` (code uses all 4; UI maps `warning`/`review` to same yellow display)
- **`RuleCheckItem`**: Individual rule check with `rule_id`, `status` (pass/fail/review), `confidence`, `detail`
- **`SecondaryRule`**: Dynamic rule with `category`, `name`, `content`, `priority`

## GUI Notes

- PySide6-Fluent-Widgets (`qfluentwidgets`) for Windows-style UI with `FluentWindow`
- QThread via `gui/utils/worker.py` for background tasks (avoids blocking UI)
- Sidebar navigation uses `addSubInterface()` and switches `QStackedWidget` pages
- Chinese font auto-detection in `main.py`
- Responsive scaling via `gui/utils/responsive.py`
- **Settings page**: Multi-API key management with add/remove/test buttons
- **Audit page**: Batch size selection (auto/3/5/8/10), compression preset

## Test Structure

- `test/test_core.py`: Module imports, schema validation, service instantiation, rules context CRUD
- `test/test_full_flow.py`: End-to-end document parsing → image audit → report generation
- `test/test_audit.py`: Integration tests for audit functionality with local images
- `test/test_deepseek.py`: DeepSeek API connectivity verification
- `test/lm_test.py`: LM Studio local model connection testing (OpenAI-compatible API)

## Prompt Templates

Audit prompts defined in `src/services/llm_service.py`:

- **`COMPRESSED_AUDIT_PROMPT`**: Single image audit - returns JSON with `results` array (simplified format)
- **`BATCH_AUDIT_PROMPT`**: Multi-image audit - returns JSON array with `idx` for each result
- **`REFERENCE_IMAGE_PROMPT`**: Instructions for LLM to compare Logo against reference images

**Simplified Output Format** (both prompts):
```json
{"id": "Rule_N", "s": "p|f|r", "c": 0.0-1.0}
```
- `s`: status (p=pass, f=fail, r=review)
- `c`: confidence (0.0-1.0)

Results sorted by status: FAIL → REVIEW → PASS in `_build_rule_checks()`.