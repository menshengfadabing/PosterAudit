# 品牌合规性智能审核平台

基于 PySide6 构建的桌面应用程序，利用大语言模型（LLM）对品牌设计稿进行智能合规性审核。

## 核心功能

### 1. 规范文档智能解析
- **多格式支持**: PDF、PPT、PPTX、DOC、DOCX、XLS、XLSX、Markdown、TXT
- **结构化提取**: 自动识别并提取品牌规范中的核心要素
  - **主要规范**: 色彩规范（主色、辅助色、禁用色）、Logo规范（位置、尺寸、安全间距）、字体规范（允许/禁用字体）
  - **次要规范**: 排版规则、文案规范、品牌调性、高风险标签等
- **多文件合并**: 支持上传多个规范文档，自动合并提取统一规则
- **流式输出**: 实时显示 LLM 解析过程，直观了解解析进度

### 2. 品牌规范管理
- **多品牌支持**: 存储和管理多个品牌的规范文档
- **快速切换**: 一键切换当前使用的品牌规范
- **规范预览**: 格式化显示规范详情，支持导出 JSON/Markdown

### 3. 设计稿智能审核
- **单图审核**: 上传单张设计稿，获取详细合规报告
- **批量审核**: 支持最多 100 张图片批量审核
  - **合并+并行策略**: 单次 API 调用处理多图 + ThreadPoolExecutor 并行处理多个批次
  - **多 Key 并发**: 支持配置多个 API Key，轮询分配避免限流
  - **动态批次优化**: 自动计算最优批次大小，最大化并行效率
  - **批次大小可选**: 自动优化/3张/4张/5张，灵活控制合并数量
- **实时流式输出**: 审核过程中实时显示 AI 分析结果
- **图片智能压缩**: 四种压缩预设（均衡/高质量/高压缩/不压缩），自动优化传输
- **精简输出格式**: 简化 LLM 输出结构，节省约 70% Token 消耗

### 4. 规则检查清单
- **逐条审核**: 将品牌规范转换为规则清单，逐条检查合规性
- **状态判定**: 根据规则状态判定最终评价（FAIL > REVIEW > PASS）
  - 有任何 FAIL → 最终评价为 **不合规**
  - 全部 PASS → 最终评价为 **合规**
  - 有 REVIEW 但无 FAIL → 最终评价为 **需复核**
- **优先级排序**: 问题优先显示（FAIL红色 → REVIEW黄色 → PASS绿色）

### 5. 报告生成与历史
- **多格式导出**: JSON、Markdown 格式报告
- **历史记录**: 自动保存每次审核结果，支持筛选查询
- **持久化存储**: 所有数据本地存储，保护隐私

## 技术架构

### 双模型架构

本系统采用两个专用模型协同工作：

| 模型 | 用途 | 特点 |
|------|------|------|
| **DeepSeek** (文本模型) | 规范文档解析 | 纯文本处理，从非结构化文档中提取结构化规则 |
| **Doubao** (多模态模型) | 设计稿审核 | 视觉理解能力，分析图片中的设计元素 |

```
┌─────────────────┐     ┌─────────────────┐
│  规范文档上传    │     │  设计稿上传      │
└────────┬────────┘     └────────┬────────┘
         │                       │
         ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│   DeepSeek      │     │    Doubao       │
│  (文本解析)      │     │  (图像审核)      │
└────────┬────────┘     └────────┬────────┘
         │                       │
         ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│  BrandRules     │◄────│  规则检查清单     │
│  (结构化规范)    │     │  RulesChecklist │
└─────────────────┘     └────────┬────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │  AuditReport    │
                        │  (审核报告)      │
                        └─────────────────┘
```

### 核心服务模块

```
src/services/
├── llm_service.py      # LLM 调用服务
│   ├── audit_image()          # 单图审核
│   ├── audit_image_stream()   # 流式审核
│   ├── audit_images_batch_stream()  # 批量审核（支持指定 API Key）
│   ├── calculate_max_images() # 动态计算批次大小
│   ├── _normalize_result()    # 标准化结果（含状态判定）
│   └── _get_next_api_key()    # API Key 轮询
│
├── document_parser.py  # 文档解析服务
│   ├── parse()                # 解析文档
│   ├── extract_text_only()    # 提取纯文本
│   └── _extract_rules_with_llm_stream()  # 流式解析
│
├── audit_service.py    # 审核编排服务
│   ├── audit()                # 执行审核
│   ├── preprocess_image()     # 图片预处理
│   ├── batch_audit_merged()   # 合并+并行批量审核（含动态批次优化）
│   └── _fallback_concurrent() # 合并失败时的并发回退
│
└── rules_context.py    # 规范上下文管理
    ├── get_rules()            # 获取规范
    ├── get_rules_checklist()  # 生成规则清单
    └── add_rules()            # 添加规范
```

### 流式输出实现

系统支持 LLM 输出的实时流式显示：

```python
# 流式调用示例
for chunk in llm_service.audit_image_stream(image, rules):
    # 实时更新UI
    streaming_display.append_text(chunk)

# 解析完整结果
result = llm_service.parse_stream_result(full_content)
```

实现原理：
1. 使用 LangChain 的 `stream()` 方法获取 LLM 输出流
2. 通过 `QMetaObject.invokeMethod` 跨线程更新 Qt UI
3. 使用 `@Slot` 装饰器注册 Qt 槽函数

### 批量审核性能优化

采用 **合并+并行** 双策略协同：

```
┌─────────────────────────────────────────────────────────────┐
│                     批量审核流程                              │
├─────────────────────────────────────────────────────────────┤
│  11张图片 + 3个API Key → 动态计算最优批次                     │
│                                                              │
│  3张/批: 4批次 → 分布3×3+2 → 2轮 → 总时间240s                │
│  4张/批: 3批次 → 分布4×2+3 → 1轮 → 总时间160s ✓ 最优         │
│  5张/批: 3批次 → 分布5×2+1 → 1轮 → 总时间200s                │
│                                                              │
│  → 选择4张/批，3批次并行执行                                  │
│                                                              │
│  批次1 ──→ API Key #1 ──→ 单次调用处理4张                    │
│  批次2 ──→ API Key #2 ──→ 单次调用处理4张  } 并发执行         │
│  批次3 ──→ API Key #3 ──→ 单次调用处理3张                    │
│                                                              │
│  优化后平均: ~14-22秒/张                                     │
└─────────────────────────────────────────────────────────────┘
```

优化点：
- **精简输出格式**: 规则结果用 `s/c` 替代 `status/confidence`，节省 ~70% Token
- **动态批次优化**: 根据图片数和 API Key 数自动计算最优批次大小
  - 目标：最小化总审核时间
  - 算法：预估各方案的总时间 = 单轮时间 × 轮数
  - 例：11张+3Key → 4张/批(160s) 比 5张/批(200s) 更快
- **不完整结果重试**: 检测输出截断，自动单独重审
- **智能结果验证**: 检查规则检查结果是否有效，而非仅看状态值

### 数据模型

核心 Pydantic 模型定义在 `src/models/schemas.py`：

```python
class BrandRules(BaseModel):
    """品牌规范"""
    brand_name: str
    color: Optional[ColorRules]      # 色彩规范
    logo: Optional[LogoRules]        # Logo规范
    font: Optional[FontRules]        # 字体规范
    secondary_rules: list[SecondaryRule]  # 次要规范

class AuditReport(BaseModel):
    """审核报告"""
    score: int                    # 合规分数（已废弃，默认为0）
    status: AuditStatus           # pass/review/fail（由规则状态判定）
    rule_checks: list[RuleCheckItem]  # 规则检查清单
    issues: list[Issue]           # 问题列表
    summary: str                  # 总体评价（含PASS/FAIL/REVIEW数量）
```

## 快速开始

### 桌面应用（PySide6）

#### 1. 环境要求

- Python >= 3.12
- uv 包管理器

#### 2. 安装依赖

```bash
uv sync
```

#### 3. 配置 API

创建 `.env` 文件：

```env
# 多模态模型（图像审核）- 支持多 Key 配置
OPENAI_API_KEY_0=your_api_key_1
OPENAI_API_KEY_1=your_api_key_2
OPENAI_API_KEY_2=your_api_key_3
OPENAI_API_BASE=https://ark.cn-beijing.volces.com/api/v3
DOUBAO_MODEL=doubao-seed-2-0-pro-260215

# 文本模型（文档解析）
DEEPSEEK_API_KEY=your_api_key
DEEPSEEK_API_BASE=https://ark.cn-beijing.volces.com/api/v3
DEEPSEEK_MODEL=deepseek-v3-2-251201

# 可选：代理配置
HTTPS_PROXY=socks5://127.0.0.1:1080
```

> **多 API Key 说明**: 配置多个 Key 后，批量审核时各批次轮询使用不同 Key，避免 API 限流。GUI 设置页面支持动态添加/测试/删除 Key。

#### 4. 运行程序

```bash
uv run python main.py
```

#### 5. 运行测试

```bash
# 核心模块测试
uv run python test/test_core.py

# 完整流程测试（需要测试数据）
uv run python test/test_full_flow.py
```

---

### Web API + Streamlit 前端（服务器部署）

平台同时提供 FastAPI REST API 和 Streamlit Web 前端，适合服务器部署和多用户访问。

#### 服务架构

```
┌──────────────┐     HTTP      ┌──────────────┐
│  Streamlit   │ ─────────── > │  FastAPI     │
│  前端        │               │  API Server  │
│  :8501       │               │  :8000       │
└──────────────┘               └──────┬───────┘
                                      │
                           ┌──────────┴──────────┐
                           │                     │
                   ┌───────▼──────┐    ┌─────────▼───────┐
                   │  PostgreSQL  │    │  文件存储         │
                   │  (任务/品牌) │    │  data/uploads/  │
                   └──────────────┘    └─────────────────┘
```

#### API 端点（9个）

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/brands` | 上传品牌规范文档并解析 |
| `GET` | `/api/v1/brands` | 列出所有品牌 |
| `PUT` | `/api/v1/brands/{id}` | 更新/重解析品牌规范 |
| `DELETE` | `/api/v1/brands/{id}` | 删除品牌 |
| `POST` | `/api/v1/brands/{id}/images` | 上传参考图片（Logo标准件）|
| `DELETE` | `/api/v1/brands/{id}/images/{filename}` | 删除参考图片 |
| `POST` | `/api/v1/audit` | 提交审核任务（支持多图）|
| `GET` | `/api/v1/tasks/{task_id}` | 查询任务状态和结果 |
| `GET` | `/api/v1/history` | 分页查询审核历史 |

#### 本地启动

```bash
# 启动 API 服务
DATABASE_URL=postgresql://user:pass@localhost/dbname uv run uvicorn web.main:app --port 8000

# 启动 Streamlit 前端（另开终端）
API_BASE_URL=http://localhost:8000 uv run streamlit run frontend/app.py --server.port 8501
```

#### Docker 部署

```bash
# 启动 API 服务（加入已有的 Docker 网络）
docker-compose -f docker-compose.web.yml up -d

# 环境变量配置（docker-compose.web.yml 中设置）
DATABASE_URL=postgresql://postgres:password@postgres:5432/brand_audit
API_KEY=your_secret_key          # 可选，不配置则无需认证
```

#### Streamlit 前端环境变量

```env
API_BASE_URL=http://localhost:8000   # API 服务地址
API_KEY=your_secret_key              # 若 API 开启认证则需要配置
```

#### Streamlit 功能页面

| 页面 | 功能 |
|------|------|
| 🔍 审核 | 上传设计稿（最多100张），选择品牌规范，查看逐规则审核结果 |
| 📋 品牌管理 | 上传规范文档、管理参考图片（Logo标准件）|
| 📁 历史 | 按品牌筛选历史任务，查看详细结果，分页浏览 |

## 项目结构

```
check_2/
├── main.py                     # 桌面应用入口
├── pyproject.toml              # 项目配置
├── build.spec                  # PyInstaller 打包配置
│
├── src/                        # 业务逻辑层（桌面和Web共用）
│   ├── models/
│   │   └── schemas.py          # Pydantic 数据模型
│   ├── services/
│   │   ├── llm_service.py      # LLM 服务（流式支持）
│   │   ├── document_parser.py  # 文档解析（流式支持）
│   │   ├── audit_service.py    # 审核服务
│   │   └── rules_context.py    # 规范管理
│   └── utils/
│       └── config.py           # 配置管理
│
├── web/                        # Web API 层（FastAPI）
│   ├── main.py                 # FastAPI 应用入口
│   ├── deps.py                 # 数据库会话、认证依赖
│   ├── models/
│   │   └── db.py               # SQLModel 数据库模型
│   └── routers/
│       ├── brands.py           # 品牌管理路由（6个端点）
│       └── audit.py            # 审核路由（3个端点）
│
├── frontend/                   # Web 前端（Streamlit）
│   ├── app.py                  # Streamlit 主入口
│   ├── config.py               # 前端配置
│   ├── api_client.py           # API 调用封装
│   └── pages/
│       ├── audit.py            # 审核页面
│       ├── brands.py           # 品牌管理页面
│       └── history.py          # 历史记录页面
│
├── gui/                        # 桌面 UI 层（PySide6）
│   ├── main_window.py          # 主窗口（FluentWindow）
│   ├── pages/
│   │   ├── audit_page.py       # 审核页面（流式显示、批次大小选择）
│   │   ├── rules_page.py       # 规范管理页面
│   │   ├── history_page.py     # 历史记录页面
│   │   └── settings_page.py    # 设置页面（多 API Key 配置）
│   ├── widgets/
│   │   ├── image_drop_area.py  # 图片拖拽组件
│   │   ├── progress_panel.py   # 进度面板
│   │   └── streaming_text_display.py  # 流式文本显示
│   └── utils/
│       ├── worker.py           # QThread 后台任务
│       └── responsive.py       # 响应式布局
│
├── docker/
│   └── web.dockerfile          # Web API Docker 镜像
├── docker-compose.web.yml      # Web API + 数据库编排
│
├── data/                       # 数据目录
│   ├── rules/                  # 品牌规范存储
│   ├── audit_history/          # 审核历史
│   ├── exports/                # 导出报告
│   └── uploads/                # 上传文件
│
└── test/                       # 测试脚本
    ├── test_core.py            # 核心模块测试
    └── test_full_flow.py       # 完整流程测试
```

## 技术栈

| 类别 | 技术 | 用途 |
|------|------|------|
| GUI 框架 | PySide6 + qfluentwidgets | 现代化 Fluent Design 界面 |
| LLM 框架 | LangChain + OpenAI API | 兼容火山引擎/豆包等 API |
| 数据验证 | Pydantic v2 | 类型安全的数据模型 |
| 文档解析 | PyMuPDF, python-pptx, python-docx | 多格式文档文本提取 |
| 图像处理 | Pillow | 图片压缩、格式转换 |
| HTTP 客户端 | httpx | 支持 SOCKS5 代理 |
| 包管理 | uv | 快速依赖管理 |

## 打包发布

```bash
# 本地打包
pyinstaller build.spec

# 跨平台发布：推送版本标签触发 GitHub Actions
git tag v1.0.0 && git push --tags
```

## 常见问题

### Q: 中文显示乱码？
程序自动检测系统中文字体。如仍有问题：
```bash
# Ubuntu/Debian
sudo apt install fonts-noto-cjk
```

### Q: 规范解析卡住？
文档解析使用 LLM，首次解析需 1-2 分钟。流式输出会实时显示解析进度。

### Q: 审核失败？
1. 检查 API Key 是否正确配置
2. 检查网络连接，必要时配置代理
3. 查看日志输出的错误信息

### Q: 如何添加新的规范规则？
上传包含新规则的文档，系统会自动提取。次要规则支持动态分类（排版、文案、风格等）。

### Q: 批量审核速度慢？
1. 配置多个 API Key（推荐 3-5 个），实现并发调用
2. 选择"自动优化"批次大小，系统会自动计算最优配置
3. 使用"均衡"或"高压缩"预设减少图片传输时间

### Q: API 限流怎么办？
配置多个 API Key，系统会轮询分配。GUI 设置页面可动态添加/测试 Key。

## License

MIT