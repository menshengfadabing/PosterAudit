# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Brand Compliance Audit Platform (品牌合规性智能审核平台) - A PySide6 desktop application that uses LLM (Doubao/Volcano Engine) to audit design materials against brand guidelines.

## Common Commands

### Development
```bash
# Install dependencies
uv sync

# Run application
uv run python main.py

# Run full flow test (requires test data files)
uv run python test/test_full_flow.py
```

### Build
```bash
# Package executable with PyInstaller
pyinstaller build.spec
```

## Architecture

### Layer Structure

```
main.py                 # Application entry point, Qt setup, font detection
├── gui/                # PySide6 UI layer
│   ├── main_window.py  # QMainWindow with sidebar navigation
│   ├── pages/          # SettingsPage, AuditPage, HistoryPage
│   └── widgets/        # Reusable components (ImageDropArea)
│
└── src/                # Business logic layer
    ├── models/         # Pydantic data models (schemas.py)
    ├── services/       # Core services (singleton instances)
    └── utils/
        └── config.py   # Pydantic-settings configuration
```

### Key Services (Singleton Pattern)

All services use global singleton instances: `llm_service`, `audit_service`, `rules_context`, `document_parser`.

- **LLMService** (`src/services/llm_service.py`): LangChain + OpenAI-compatible API. Handles single/batch image audit with token estimation and context window management.
- **AuditService** (`src/services/audit_service.py`): Image preprocessing (compression, resize), audit orchestration. Two batch modes: concurrent API calls or merged single request.
- **DocumentParser** (`src/services/document_parser.py`): Extracts text from PDF (PyMuPDF), PPT (python-pptx), Word (python-docx), Excel (openpyxl/xlrd), Markdown, then uses LLM to parse into structured `BrandRules`.
- **RulesContextManager** (`src/services/rules_context.py`): Singleton managing brand rules cache and persistence in `data/rules/`.

### Dual-Model Architecture

The application uses two separate LLM endpoints:

1. **DeepSeek** (text-only): Parses brand guideline documents into structured rules
   - Config: `deepseek_api_key`, `deepseek_api_base`, `deepseek_model`
   - Used by `DocumentParser._extract_rules_with_llm()`

2. **Doubao** (multimodal): Audits images against brand rules
   - Config: `openai_api_key`, `openai_api_base`, `doubao_model`
   - Used by `LLMService.audit_image()` and `LLMService.audit_images_batch()`

### Batch Audit Strategies

`AuditService` provides two batch modes:

- **`batch_audit_concurrent()`**: Multiple parallel API calls (default `max_concurrent=5`)
- **`batch_audit_merged()`**: Single merged request with multiple images, auto-calculates max images per request based on token limits

The merged mode uses `LLMService.calculate_max_images()` for dynamic batch sizing based on context window and output token limits.

### Data Flow

1. **Upload brand guidelines** → DocumentParser extracts text → DeepSeek LLM parses into BrandRules → RulesContextManager stores
2. **Audit image** → AuditService preprocesses (compress/resize) → Doubao LLM calls API with rules context → AuditReport returned

### Configuration

- Environment variables via `.env` file (see `.env.example`)
- Required: `OPENAI_API_KEY`, `OPENAI_API_BASE`, `DOUBAO_MODEL` for image audit
- Required: `DEEPSEEK_API_KEY`, `DEEPSEEK_API_BASE`, `DEEPSEEK_MODEL` for document parsing
- Data directories: `data/rules/`, `data/audit_history/`, `data/exports/`, `data/uploads/`

## Key Data Models

See `src/models/schemas.py`:
- `BrandRules`: Brand guidelines (color, logo, font, copywriting, layout rules)
- `AuditReport`: Audit result (score, status, detection, checks, issues)
- `DetectionResult`: Detected elements (colors, logo, texts, fonts, layout)

## GUI Notes

- Uses QThread for background tasks (`gui/utils/worker.py`)
- Navigation via sidebar QListWidget switching QStackedWidget pages
- Chinese font auto-detection in `main.py` for cross-platform support