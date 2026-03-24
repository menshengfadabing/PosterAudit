(check-2) admin123@peixu7-gy:~/project/AI_project/check_2$ uv run python main.py
2026-03-24 17:36:28,055 [INFO] __main__: 品牌合规审核平台启动...
2026-03-24 17:36:28,318 [INFO] src.services.rules_context: 已加载默认规范: 示例品牌
2026-03-24 17:36:28,427 [INFO] src.services.rules_context: 当前品牌已切换: default
2026-03-24 17:36:28,427 [INFO] src.services.rules_context: 当前品牌已切换: default
2026-03-24 17:37:55,095 [INFO] src.services.audit_service: 使用压缩预设: balanced
2026-03-24 17:37:55,096 [INFO] gui.pages.audit_page: 使用压缩预设: balanced
2026-03-24 17:37:55,103 [INFO] gui.pages.audit_page: 开始批量审核（合并请求模式），共 7 张图片
2026-03-24 17:37:55,103 [INFO] src.services.audit_service: 开始合并请求批量审核: 7张图片
2026-03-24 17:37:55,228 [INFO] src.services.audit_service: 图片缩放: (3840, 2160) -> (1920, 1080)
2026-03-24 17:37:55,236 [INFO] src.services.audit_service: 图片压缩完成: 1173.5KB -> 197.2KB (节省83.2%)
2026-03-24 17:37:55,319 [INFO] src.services.audit_service: 图片缩放: (3840, 2160) -> (1920, 1080)
2026-03-24 17:37:55,327 [INFO] src.services.audit_service: 图片压缩完成: 1188.6KB -> 246.4KB (节省79.3%)
2026-03-24 17:37:55,329 [INFO] src.services.audit_service: 图片压缩完成: 19.4KB -> 15.9KB (节省18.3%)
2026-03-24 17:37:55,419 [INFO] src.services.audit_service: 图片压缩完成: 28.1KB -> 58.2KB (节省-107.2%)
2026-03-24 17:37:55,433 [INFO] src.services.audit_service: 图片压缩完成: 226.9KB -> 149.8KB (节省34.0%)
2026-03-24 17:37:55,470 [INFO] src.services.audit_service: 图片缩放: (1280, 2528) -> (972, 1920)
2026-03-24 17:37:55,477 [INFO] src.services.audit_service: 图片压缩完成: 285.7KB -> 174.8KB (节省38.8%)
2026-03-24 17:37:55,506 [INFO] src.services.audit_service: 图片缩放: (1080, 1933) -> (1072, 1920)
2026-03-24 17:37:55,513 [INFO] src.services.audit_service: 图片压缩完成: 127.2KB -> 139.1KB (节省-9.4%)
2026-03-24 17:37:55,514 [INFO] src.services.llm_service: 上下文窗口: 128000, 可用: 126378, 可容纳图片: 7
2026-03-24 17:37:55,514 [INFO] src.services.audit_service: 动态计算: 单次请求最多可处理 7 张图片
2026-03-24 17:37:55,514 [INFO] src.services.audit_service: 分为 1 批次处理
2026-03-24 17:37:55,514 [INFO] src.services.audit_service: 处理第 1/1 批，共 7 张图片
2026-03-24 17:37:55,514 [INFO] src.services.llm_service: 批量审核: 单次API调用处理 7 张图片
2026-03-24 17:37:55,515 [INFO] src.services.llm_service: 正在调用API进行批量审核...
2026-03-24 17:40:06,400 [WARNING] src.services.llm_service: 批量响应解析不完整，预期7个结果，实际解析0个
2026-03-24 17:40:06,400 [INFO] src.services.audit_service: 批次 1 完成，耗时: 130.9秒
2026-03-24 17:40:06,400 [INFO] src.services.audit_service: 合并请求批量审核完成: 总耗时: 131.3秒, 平均每张: 18.8秒
2026-03-24 17:40:06,400 [INFO] gui.pages.audit_page: 批量审核完成，耗时: 131.3秒，平均每张: 18.8秒
