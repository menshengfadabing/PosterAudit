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
- **Logo参考图片**: 每个规范组可上传最多5张标准Logo参考图片，审核时作为视觉对照发送给多模态模型

### 3. 设计稿智能审核
- **单图审核**: 上传单张设计稿，获取详细合规报告
- **批量审核**: 支持最多 100 张图片批量审核
  - **并发模式**: 多个独立 API 请求并行处理，速度快
  - **合并模式**: 单次 API 调用处理多图，节省 Token
- **实时流式输出**: 审核过程中实时显示 AI 分析结果
- **图片智能压缩**: 四种压缩预设（均衡/高质量/高压缩/不压缩），自动优化传输

### 4. 规则检查清单
- **逐条审核**: 将品牌规范转换为规则清单，逐条检查合规性
- **状态标识**: 每条规则标注结果（PASS/REVIEW/FAIL）和置信度
  - **PASS**: 合规，置信度通常 0.8-1.0
  - **FAIL**: 不合规，需修改
  - **REVIEW**: 需人工复核，置信度可能较低（软规则或需语境判断）
- **优先级排序**: 问题规则优先显示，便于快速定位
- **置信度说明**: 置信度表示 LLM 对判断的确定性（0-1），高风险标签等软规则默认进入人工复核

### 5. 报告生成与历史
- **多格式导出**: JSON、Markdown 格式报告
- **统一导出格式**: `[状态] Rule_ID : 规则内容 -->> 状态 >> 参考文档，置信度：0.XX；`
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
│   └── audit_images_batch()   # 批量审核
│
├── document_parser.py  # 文档解析服务
│   ├── parse()                # 解析文档
│   ├── extract_text_only()    # 提取纯文本
│   └── _extract_rules_with_llm_stream()  # 流式解析
│
├── audit_service.py    # 审核编排服务
│   ├── audit()                # 执行审核
│   ├── preprocess_image()     # 图片预处理
│   ├── batch_audit_concurrent()  # 并发批量
│   └── batch_audit_merged()   # 合并批量
│
└── rules_context.py    # 规范上下文管理
    ├── get_rules()            # 获取规范
    ├── get_rules_checklist()  # 生成规则清单
    ├── add_rules()            # 添加规范
    ├── add_reference_image()  # 添加Logo参考图片
    ├── get_reference_images() # 获取参考图片列表
    └── delete_reference_image() # 删除参考图片
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

### 数据模型

核心 Pydantic 模型定义在 `src/models/schemas.py`：

```python
class ReferenceImage(BaseModel):
    """标准参考图片（Logo等）"""
    filename: str              # 文件名
    description: str           # 图片描述
    image_type: str            # 图片类型：logo/logo_variant/icon等
    file_size: int             # 文件大小(字节)
    upload_time: datetime      # 上传时间

class BrandRules(BaseModel):
    """品牌规范"""
    brand_name: str
    color: Optional[ColorRules]      # 色彩规范
    logo: Optional[LogoRules]        # Logo规范
    font: Optional[FontRules]        # 字体规范
    secondary_rules: list[SecondaryRule]  # 次要规范
    reference_images: list[ReferenceImage]  # Logo参考图片列表

class AuditReport(BaseModel):
    """审核报告"""
    score: int                    # 合规分数 0-100
    status: AuditStatus           # pass/review/fail
    rule_checks: list[RuleCheckItem]  # 规则检查清单
    issues: list[Issue]           # 问题列表
    summary: str                  # 总体评价
```

### 审核状态说明

系统统一使用三种审核状态：
- **pass**: 合规通过
- **review**: 需人工复核（高风险标签、语义判断、场景适配等）
- **fail**: 不合规，需修改

## 快速开始

### 1. 环境要求

- Python >= 3.12
- uv 包管理器

### 2. 安装依赖

```bash
uv sync
```

### 3. 配置 API

创建 `.env` 文件：

```env
# 多模态模型（图像审核）
OPENAI_API_KEY=your_api_key
OPENAI_API_BASE=https://ark.cn-beijing.volces.com/api/v3
DOUBAO_MODEL=doubao-seed-2-0-pro-260215

# 文本模型（文档解析）
DEEPSEEK_API_KEY=your_api_key
DEEPSEEK_API_BASE=https://ark.cn-beijing.volces.com/api/v3
DEEPSEEK_MODEL=deepseek-v3-2-251201

# 可选：代理配置
HTTPS_PROXY=socks5://127.0.0.1:1080
```

### 4. 运行程序

```bash
uv run python main.py
```

### 5. 运行测试

```bash
# 核心模块测试
uv run python test/test_core.py

# 完整流程测试（需要测试数据）
uv run python test/test_full_flow.py
```

## 项目结构

```
check_2/
├── main.py                     # 应用入口
├── pyproject.toml              # 项目配置
├── build.spec                  # PyInstaller 打包配置
│
├── src/                        # 业务逻辑层
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
├── gui/                        # UI 层
│   ├── main_window.py          # 主窗口（FluentWindow）
│   ├── pages/
│   │   ├── audit_page.py       # 审核页面（流式显示）
│   │   ├── rules_page.py       # 规范管理页面
│   │   ├── history_page.py     # 历史记录页面
│   │   └── settings_page.py    # 设置页面
│   ├── widgets/
│   │   ├── image_drop_area.py  # 图片拖拽组件
│   │   ├── progress_panel.py   # 进度面板
│   │   └── streaming_text_display.py  # 流式文本显示
│   └── utils/
│       ├── worker.py           # QThread 后台任务
│       └── responsive.py       # 响应式布局
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

## License

MIT

## 更新日志

### v1.1.2
- 新增 Logo 参考图片功能：每个规范组可上传最多5张标准Logo图片，审核时作为视觉对照
- 统一审核状态为三种：pass/review/fail（移除 warning 状态）
- 修复批量导出报告缺少参考文档和置信度的 bug
- 优化导出报告格式统一性

### v1.1.1
- 修复 Logo 参考图片在审核时不生效的 bug
- 优化规范管理页面删除按钮显示