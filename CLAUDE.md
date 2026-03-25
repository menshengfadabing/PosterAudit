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

# Run full flow test
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
    ├── services/       # Core services
    │   ├── llm_service.py       # LLM API calls via LangChain
    │   ├── document_parser.py   # PDF/PPT/Word/Excel parsing
    │   ├── audit_service.py     # Image preprocessing + audit orchestration
    │   └── rules_context.py     # Brand rules management
    └── utils/
        └── config.py   # Pydantic-settings configuration
```

### Key Services

- **LLMService**: LangChain + OpenAI-compatible API (Doubao). Handles single/batch image audit with token estimation and context window management.
- **DocumentParser**: Extracts text from PDF (PyMuPDF), PPT (python-pptx), Word (python-docx), Excel (openpyxl/xlrd), then uses LLM to parse into structured `BrandRules`.
- **AuditService**: Image preprocessing (compression, resize), audit orchestration. Two batch modes: concurrent API calls or merged single request.
- **RulesContextManager**: Singleton managing brand rules cache and persistence in `data/rules/`.

### Data Flow

1. **Upload brand guidelines** → DocumentParser extracts text → LLM parses into BrandRules → RulesContextManager stores
2. **Audit image** → AuditService preprocesses → LLMService calls API with rules context → AuditReport returned

### Configuration

- Environment variables via `.env` file (see `.env.example`)
- `OPENAI_API_KEY`, `OPENAI_API_BASE`, `DOUBAO_MODEL` required for LLM
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