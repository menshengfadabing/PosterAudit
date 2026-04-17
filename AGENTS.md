# Repository Guidelines
A PySide6-based desktop application for intelligent brand compliance auditing using LLMs.


## Project Structure and Module Organization

- main.py - Application entry point
- src/ - Business logic layer (models/schemas.py, services/, utils/config.py)
- test/ - Test scripts (test_core.py, test_full_flow.py)
- gui/ - UI layer with pages/, widgets/, utils/ (PySide6 + qfluentwidgets)
- data/ - Runtime data (rules/, audit_history/, exports/, uploads/)
- config/ - Configuration files

## Build, Test, and Development Commands

- Install dependencies: uv sync
- Run application: uv run python main.py
- Run tests: uv run python test/test_core.py or test/test_full_flow.py
- Build executable: ./build.sh or pyinstaller build.spec
- Release: git tag v1.0.0 && git push --tags triggers GitHub Actions

## Coding Style and Naming Conventions

- Python 3.12+ with type hints required
- Pydantic v2 BaseModel for data structures
- str, Enum pattern for type-safe enums
- Imports: standard library, third-party, local modules
- snake_case for files/functions/variables, PascalCase for classes
- Chinese comments accepted; document public functions and classes

## Testing Guidelines

- All tests in test/ directory as standalone scripts
- Run with: uv run python test/test_file.py
- Key tests: test_core.py (models, services), test_full_flow.py (end-to-end)

## Commit and Pull Request Guidelines

- Commit messages: concise Chinese descriptions
- Semantic versioning tags (v1.0.0, v1.1.0) for releases
- PR descriptions: purpose, testing performed, breaking changes

## Architecture Notes

- Dual LLM: DeepSeek for document parsing, Doubao (multimodal) for image auditing
- Streaming output via LangChain stream() method
- Thread-safe UI updates with QMetaObject.invokeMethod
- Local JSON storage in data/ directory

## Environment Configuration

Create .env file based on .env.example:
- DEEPSEEK_API_KEY, DEEPSEEK_API_BASE, DEEPSEEK_MODEL (document parsing)
- OPENAI_API_KEY, OPENAI_API_BASE, DOUBAO_MODEL (image auditing)
- Optional: HTTPS_PROXY for network proxy

