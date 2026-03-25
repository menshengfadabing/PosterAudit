2026-03-25 10:26:59,167 [INFO] gui.pages.audit_page: 开始批量审核（合并请求模式），共 7 张图片
2026-03-25 10:26:59,167 [INFO] src.services.audit_service: 开始合并请求批量审核: 7张图片
2026-03-25 10:26:59,266 [INFO] src.services.audit_service: 图片缩放: (3840, 2160) -> (1920, 1080)
2026-03-25 10:26:59,273 [INFO] src.services.audit_service: 图片压缩完成: 1173.5KB -> 197.2KB (节省83.2%)
2026-03-25 10:26:59,367 [INFO] src.services.audit_service: 图片缩放: (3840, 2160) -> (1920, 1080)
2026-03-25 10:26:59,376 [INFO] src.services.audit_service: 图片压缩完成: 1188.6KB -> 246.4KB (节省79.3%)
2026-03-25 10:26:59,377 [INFO] src.services.audit_service: 图片压缩完成: 19.4KB -> 15.9KB (节省18.3%)
2026-03-25 10:26:59,405 [INFO] src.services.audit_service: 图片缩放: (1080, 1933) -> (1072, 1920)
2026-03-25 10:26:59,412 [INFO] src.services.audit_service: 图片压缩完成: 127.2KB -> 139.1KB (节省-9.4%)
2026-03-25 10:26:59,454 [INFO] src.services.audit_service: 图片压缩完成: 28.1KB -> 58.2KB (节省-107.2%)
2026-03-25 10:26:59,469 [INFO] src.services.audit_service: 图片压缩完成: 226.9KB -> 149.8KB (节省34.0%)
2026-03-25 10:26:59,507 [INFO] src.services.audit_service: 图片缩放: (1280, 2528) -> (972, 1920)
2026-03-25 10:26:59,513 [INFO] src.services.audit_service: 图片压缩完成: 285.7KB -> 174.8KB (节省38.8%)
2026-03-25 10:26:59,514 [INFO] src.services.llm_service: 动态计算: 输入限制=7张, 输出限制=6张, 最终=6张 (上下文128000, 输出限制8192)
2026-03-25 10:26:59,514 [INFO] src.services.audit_service: 分为 2 批次处理
2026-03-25 10:26:59,514 [INFO] src.services.audit_service: 处理第 1/2 批，共 6 张图片
2026-03-25 10:26:59,514 [INFO] src.services.llm_service: 批量审核: 单次API调用处理 6 张图片
2026-03-25 10:26:59,514 [INFO] src.services.llm_service: 正在调用API进行批量审核...
2026-03-25 10:28:49,124 [WARNING] src.services.llm_service: JSON解析失败: Unterminated string starting at: line 241 column 68 (char 11397)
2026-03-25 10:28:49,124 [WARNING] src.services.llm_service: 正则提取后JSON解析失败: Expecting ',' delimiter: line 239 column 14 (char 11298)
2026-03-25 10:28:49,124 [ERROR] src.services.llm_service: 批量响应解析完全失败，预期6个结果
2026-03-25 10:28:49,124 [ERROR] src.services.llm_service: 响应内容长度: 11398, 前500字符: [
    {
        "image_index": 0,
        "score": 40,
        "status": "fail",
        "detection": {
            "colors": [
                {"hex": "#E6212A", "name": "红色", "percent": 80},
                {"hex": "#FFD700", "name": "金色", "percent": 15},
                {"hex": "#FFFFFF", "name": "白色", "percent": 5}
            ],
            "logo": {"found": true, "position": "左下角", "size_percent": 8, "position_correct": false},
            "texts": ["颁奖典礼", "2025-2026年度技术中心总结&计划报告暨表彰大会", "
2026-03-25 10:28:49,125 [INFO] src.services.audit_service: 批次 1 完成，耗时: 109.6秒
2026-03-25 10:28:49,125 [WARNING] src.services.audit_service: 批次 1 合并请求全部失败，回退到并发单图审核
2026-03-25 10:28:49,125 [INFO] src.services.llm_service: 正在调用API进行审核...