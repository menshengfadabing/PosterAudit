# 品牌合规审核平台

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置API

首次运行时，需要在「设置」页面配置：
- API Key: 豆包/火山引擎 API密钥
- API地址: 默认为火山引擎地址
- 模型: 默认为 doubao-seed-2-0-pro-260215

### 3. 运行程序

```bash
python main.py
```

## 功能说明

1. **设置**: 配置API、管理品牌规范
2. **设计审核**: 上传设计稿进行品牌合规审核
3. **报告历史**: 查看历史审核记录

## 打包发布

```bash
pyinstaller build.spec
```

生成的可执行文件位于 `dist/BrandAudit.exe`

## 目录结构

```
check_2/
├── src/                 # 核心业务代码
│   ├── services/        # 服务层
│   ├── models/          # 数据模型
│   └── utils/           # 工具函数
├── gui/                 # PySide6界面
│   ├── pages/           # 页面
│   ├── widgets/         # 组件
│   └── utils/           # 工具
├── config/              # 配置文件
├── data/                # 数据目录
├── main.py              # 程序入口
└── requirements.txt     # 依赖列表
```