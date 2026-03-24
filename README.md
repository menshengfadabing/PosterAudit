# 品牌合规性智能审核平台

基于 PySide6 构建的桌面应用程序，用于品牌设计稿的合规性审核。

## 功能特性

- **规范文档解析**: 支持 PDF/PPT 格式的品牌规范文档上传与智能解析
- **品牌规范管理**: 多品牌规范存储、切换与管理
- **智能审核**: 基于 LLM 的设计稿品牌合规审核
- **批量审核**: 支持多图片批量审核，实时进度显示
- **报告生成**: JSON/Markdown 格式报告导出
- **历史记录**: 审核历史持久化存储与查询

## 快速开始

### 1. 环境要求

- Python >= 3.12
- uv 包管理器

### 2. 安装依赖

```bash
uv sync
```

### 3. 配置 API

首次运行时，在「系统设置」→「API配置」页面配置：

| 配置项 | 说明 |
|--------|------|
| API Key | 豆包/火山引擎 API 密钥 |
| API 地址 | 默认: `https://ark.cn-beijing.volces.com/api/v3` |
| 模型名称 | 默认: `doubao-seed-2-0-pro-260215` |

支持通过环境变量配置，创建 `.env` 文件：

```env
OPENAI_API_KEY=your_api_key
OPENAI_API_BASE=https://ark.cn-beijing.volces.com/api/v3
DOUBAO_MODEL=doubao-seed-2-0-pro-260215
```

### 4. 运行程序

```bash
uv run python main.py
```

## 使用指南

### 规范管理

1. 进入「系统设置」→「规范管理」
2. 点击「上传规范文档 (PDF/PPT)」上传品牌规范文件
3. 系统自动解析并提取规范内容（Logo、色彩、字体等）
4. 选择规范后点击「设为当前」激活使用

### 单图审核

1. 进入「设计审核」→「单图审核」
2. 选择品牌规范
3. 拖拽或点击上传设计稿图片
4. 点击「开始审核」，等待结果
5. 查看审核分数、检测结果、问题列表
6. 可导出 JSON/Markdown 报告

### 批量审核

1. 进入「设计审核」→「批量审核」
2. 选择品牌规范
3. 上传多张图片（最多 100 张）
4. 点击「开始批量审核」
5. 查看批量审核摘要与结果列表

### 历史记录

- 自动保存每次审核结果
- 支持筛选、导出、清空操作
- 数据持久化存储在 `data/audit_history/` 目录

## 项目结构

```
check_2/
├── main.py                 # 程序入口
├── pyproject.toml          # 项目配置与依赖
├── src/                    # 核心业务代码
│   ├── models/             # Pydantic 数据模型
│   │   └── schemas.py      # BrandRules, AuditReport 等
│   ├── services/           # 业务服务
│   │   ├── llm_service.py      # LLM 调用服务
│   │   ├── document_parser.py  # 文档解析服务
│   │   ├── audit_service.py    # 审核服务
│   │   └── rules_context.py    # 规范上下文管理
│   └── utils/              # 工具函数
│       └── config.py       # 配置管理
├── gui/                    # PySide6 界面
│   ├── main_window.py      # 主窗口
│   ├── pages/              # 功能页面
│   │   ├── settings_page.py    # 设置页面
│   │   ├── audit_page.py       # 审核页面
│   │   └── history_page.py     # 历史页面
│   ├── widgets/            # 自定义组件
│   │   └── image_drop_area.py  # 图片拖拽上传组件
│   └── utils/              # 界面工具
│       └── worker.py       # 后台任务工作线程
├── data/                   # 数据目录
│   ├── rules/              # 品牌规范存储
│   ├── audit_history/      # 审核历史记录
│   ├── exports/            # 导出报告目录
│   └── uploads/            # 上传文件目录
├── test/                   # 测试脚本
│   └── test_full_flow.py   # 完整流程测试
└── docs/                   # 文档
```

## 技术栈

- **GUI 框架**: PySide6 (Qt for Python)
- **LLM 框架**: LangChain + OpenAI API 兼容接口
- **数据验证**: Pydantic v2
- **文档解析**: PyMuPDF (PDF), python-pptx (PPT)
- **图像处理**: Pillow
- **HTTP 客户端**: httpx (支持 SOCKS 代理)
- **包管理**: uv

## 打包发布

```bash
pyinstaller build.spec
```

生成的可执行文件位于 `dist/` 目录。

## 代理配置

支持 SOCKS5 代理，在 `.env` 中配置：

```env
HTTPS_PROXY=socks5://127.0.0.1:1080
```

## 常见问题

### Q: 中文显示乱码？

程序会自动检测系统中的中文字体（Noto Sans CJK SC、WenQuanYi Micro Hei、Microsoft YaHei 等）。如仍有问题，请安装中文字体：

```bash
# Ubuntu/Debian
sudo apt install fonts-noto-cjk

# 或
sudo apt install fonts-wqy-microhei
```

### Q: 上传规范解析卡住？

文档解析使用 LLM，首次解析可能需要 1-2 分钟。解析过程在后台线程执行，不会阻塞界面。

### Q: 规范详情显示原始文本？

当 LLM 未能成功提取结构化规范时，会显示文档的原始文本内容，仍可用于审核参考。

## 开发说明

### 运行测试

```bash
uv run python test/test_full_flow.py
```

### 代码风格

- 使用 Python 3.12+ 语法
- 类型注解
- Pydantic 模型进行数据验证
- QThread 后台执行耗时操作

## License

MIT