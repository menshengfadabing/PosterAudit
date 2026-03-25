(check-2) admin123@peixu7-gy:~/project/AI_project/check_2$ uv run python main.py
2026-03-25 14:38:27,669 [INFO] __main__: 品牌合规审核平台启动...
2026-03-25 14:38:27,966 [INFO] src.services.rules_context: 已加载默认规范: 示例品牌
2026-03-25 14:38:28,125 [INFO] src.services.rules_context: 当前品牌已切换: default
2026-03-25 14:38:28,125 [INFO] src.services.rules_context: 当前品牌已切换: default
2026-03-25 14:38:33,207 [INFO] src.services.rules_context: 当前品牌已切换: brand_ab4c4ac4
2026-03-25 14:39:27,288 [INFO] src.services.document_parser: 解析PDF文档: 讯飞品牌设计标准.pdf
2026-03-25 14:39:27,334 [INFO] src.services.document_parser: PDF解析完成，共37页，9074字符
2026-03-25 14:39:28,162 [INFO] src.services.document_parser: 使用LLM提取品牌规范: 讯飞品牌设计标准.pdf
2026-03-25 14:39:28,162 [INFO] src.services.document_parser: DeepSeek API配置: base=https://ark.cn-beijing.volces.com/api/v3, model=deepseek-v3-2-251201
2026-03-25 14:39:28,435 [INFO] src.services.document_parser: 正在调用LLM...
2026-03-25 14:39:36,313 [INFO] src.services.document_parser: LLM响应长度: 611 字符
2026-03-25 14:39:36,313 [INFO] src.services.document_parser: LLM规则提取完成: brand_name=iFLYTEK, color=True, logo=True, font=True
2026-03-25 14:39:36,314 [INFO] src.services.rules_context: 添加品牌规范: brand_af74dbe0 - 讯飞品牌
2026-03-25 14:39:39,286 [INFO] src.services.rules_context: 当前品牌已切换: default
2026-03-25 14:39:39,287 [INFO] src.services.rules_context: 当前品牌已切换: default
2026-03-25 14:40:34,814 [INFO] src.services.audit_service: 使用压缩预设: balanced
2026-03-25 14:40:34,814 [INFO] gui.pages.audit_page: 单图审核使用压缩预设: balanced
2026-03-25 14:40:34,822 [INFO] src.services.audit_service: 预处理图片...
2026-03-25 14:40:34,837 [INFO] src.services.audit_service: 图片压缩完成: 19.4KB -> 15.9KB (节省18.3%)
2026-03-25 14:40:34,838 [INFO] src.services.audit_service: 调用LLM审核...
2026-03-25 14:40:34,838 [INFO] src.services.llm_service: 正在调用API进行审核...
2026-03-25 14:42:52,578 [INFO] src.services.audit_service: 使用压缩预设: balanced
2026-03-25 14:42:52,578 [INFO] gui.pages.audit_page: 使用压缩预设: balanced
2026-03-25 14:42:52,591 [INFO] gui.pages.audit_page: 开始批量审核（合并请求模式），共 4 张图片
2026-03-25 14:42:52,591 [INFO] src.services.audit_service: 开始合并请求批量审核: 4张图片
2026-03-25 14:42:52,704 [INFO] src.services.audit_service: 图片缩放: (3840, 2160) -> (1920, 1080)
2026-03-25 14:42:52,713 [INFO] src.services.audit_service: 图片压缩完成: 1173.5KB -> 197.2KB (节省83.2%)
2026-03-25 14:42:52,815 [INFO] src.services.audit_service: 图片缩放: (3840, 2160) -> (1920, 1080)
2026-03-25 14:42:52,823 [INFO] src.services.audit_service: 图片压缩完成: 1188.6KB -> 246.4KB (节省79.3%)
2026-03-25 14:42:52,825 [INFO] src.services.audit_service: 图片压缩完成: 19.4KB -> 15.9KB (节省18.3%)
2026-03-25 14:42:52,860 [INFO] src.services.audit_service: 图片缩放: (1080, 1933) -> (1072, 1920)
2026-03-25 14:42:52,867 [INFO] src.services.audit_service: 图片压缩完成: 127.2KB -> 139.1KB (节省-9.4%)
2026-03-25 14:42:52,868 [INFO] src.services.llm_service: 动态计算: 输入限制=4张, 输出限制=3张, 最终=3张 (上下文128000, 输出限制8192)
2026-03-25 14:42:52,868 [INFO] src.services.audit_service: 分为 2 批次处理
2026-03-25 14:42:52,868 [INFO] src.services.audit_service: 处理第 1/2 批，共 3 张图片
2026-03-25 14:42:52,868 [INFO] src.services.llm_service: 批量审核: 单次API调用处理 3 张图片
2026-03-25 14:42:52,868 [INFO] src.services.llm_service: 正在调用API进行批量审核...
2026-03-25 14:45:13,203 [INFO] src.services.llm_service: 批量解析成功: 3个结果
2026-03-25 14:45:13,203 [INFO] src.services.audit_service: 批次 1 完成，耗时: 140.3秒
2026-03-25 14:45:13,204 [INFO] src.services.audit_service: 处理第 2/2 批，共 1 张图片
2026-03-25 14:45:13,204 [INFO] src.services.llm_service: 正在调用API进行审核...
2026-03-25 14:45:59,581 [INFO] src.services.audit_service: 批次 2 完成，耗时: 46.4秒
2026-03-25 14:45:59,581 [INFO] src.services.audit_service: 合并请求批量审核完成: 总耗时: 187.0秒, 平均每张: 46.7秒
2026-03-25 14:45:59,581 [INFO] gui.pages.audit_page: 批量审核完成，耗时: 187.0秒，平均每张: 46.7秒