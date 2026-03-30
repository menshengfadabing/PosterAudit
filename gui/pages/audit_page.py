"""审核页面 - 统一的审核界面"""

import json
import logging
from pathlib import Path
from datetime import datetime
import uuid
from PySide6.QtCore import Qt, Signal, Slot, QMetaObject, Q_ARG
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFileDialog

from qfluentwidgets import (
    ScrollArea, StrongBodyLabel, CaptionLabel, BodyLabel,
    PushButton, PrimaryPushButton, ComboBox,
    ProgressBar, TextEdit,
    InfoBar, InfoBarPosition, MessageBox, CardWidget,
    FluentIcon as FIF, TitleLabel
)

from gui.widgets import ImageDropArea
from gui.widgets.streaming_text_display import StreamingAuditDisplay
from gui.utils import Worker
from src.services.audit_service import audit_service
from src.services.rules_context import rules_context
from src.utils.config import get_app_dir

logger = logging.getLogger(__name__)


class AuditPage(ScrollArea):
    """审核页面 - 统一的单图/批量审核界面"""

    # 进度信号: (percent, message, log_message)
    progress_updated = Signal(int, str, str)
    task_started = Signal(str)  # 任务名称
    task_finished = Signal(bool, str)  # 成功/失败, 消息
    # 流式结果信号: (result, index, completed, total)
    streaming_result = Signal(dict, int, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("auditPage")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.audit_result = None
        self._init_ui()

    def showEvent(self, event):
        """页面显示时自动刷新品牌列表"""
        super().showEvent(event)
        self._load_brand_list()

    def _init_ui(self):
        # 主容器
        self.view = QWidget()
        self.setWidget(self.view)

        layout = QVBoxLayout(self.view)
        layout.setContentsMargins(36, 20, 36, 20)
        layout.setSpacing(20)

        # 标题
        title = TitleLabel("设计稿审核")
        layout.addWidget(title)

        # 提示信息
        hint = CaptionLabel("上传单张或多张设计稿进行品牌合规审核（上传多张自动触发批量审核）")
        layout.addWidget(hint)

        # 主内容区
        content_layout = QHBoxLayout()
        content_layout.setSpacing(16)

        # 左侧：设置区域
        left_card = CardWidget()
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(20, 20, 20, 20)
        left_layout.setSpacing(16)

        # 审核设置
        settings_label = StrongBodyLabel("审核设置")
        left_layout.addWidget(settings_label)

        # 品牌选择
        brand_layout = QHBoxLayout()
        brand_label = BodyLabel("品牌规范:")
        self.brand_combo = ComboBox()
        brand_layout.addWidget(brand_label)
        brand_layout.addWidget(self.brand_combo, 1)
        left_layout.addLayout(brand_layout)

        # 压缩预设选择
        compression_layout = QHBoxLayout()
        compression_label = BodyLabel("图片压缩:")
        self.compression_combo = ComboBox()
        self.compression_combo.addItems([
            "均衡（推荐）",
            "高质量",
            "高压缩",
            "不压缩"
        ])
        self.compression_combo.setToolTip(
            "均衡：1920px/500KB/75%，适合大多数场景\n"
            "高质量：2560px/1MB/90%，保留更多细节\n"
            "高压缩：1280px/300KB/60%，最小传输量\n"
            "不压缩：原图传输，消耗更多Token"
        )
        compression_layout.addWidget(compression_label)
        compression_layout.addWidget(self.compression_combo, 1)
        left_layout.addLayout(compression_layout)

        # 图片选择 - 支持多选
        image_label = StrongBodyLabel("设计稿图片")
        left_layout.addWidget(image_label)

        self.image_drop = ImageDropArea(multi_select=True, max_images=100)
        self.image_drop.images_selected.connect(self._on_images_selected)
        left_layout.addWidget(self.image_drop)

        # 文件计数
        self.file_count_label = CaptionLabel("已选择 0 张图片")
        left_layout.addWidget(self.file_count_label)

        # 操作按钮
        self.audit_btn = PrimaryPushButton("开始审核")
        self.audit_btn.clicked.connect(self._on_audit)
        self.audit_btn.setEnabled(False)
        left_layout.addWidget(self.audit_btn)

        # 进度
        self.progress_bar = ProgressBar()
        self.progress_bar.setVisible(False)
        left_layout.addWidget(self.progress_bar)

        self.status_label = CaptionLabel("")
        self.status_label.setWordWrap(True)
        left_layout.addWidget(self.status_label)

        left_layout.addStretch()
        content_layout.addWidget(left_card, 2)

        # 右侧：结果展示（直接放置streaming_display，不再嵌套CardWidget）
        self.streaming_display = StreamingAuditDisplay(
            max_height=400,
            show_export=True
        )
        self.streaming_display.set_title("审核结果")
        self.streaming_display.set_export_callbacks(self._on_export_json, self._on_export_md)
        # 设置占位文本，当没有内容时显示
        self.streaming_display.text_edit.setPlaceholderText("请上传图片开始审核")
        content_layout.addWidget(self.streaming_display, 3)

        layout.addLayout(content_layout, 1)

        # 加载品牌列表
        self._load_brand_list()

    def _load_brand_list(self):
        """加载品牌列表"""
        self.brand_combo.clear()

        rules_list = rules_context.list_rules()
        for rule in rules_list:
            brand_id = rule.get("brand_id", "")
            brand_name = rule.get("brand_name", "未命名")
            self.brand_combo.addItem(brand_name, brand_id)

    def _on_images_selected(self, image_paths: list):
        """图片选择回调"""
        count = len(image_paths)
        self.file_count_label.setText(f"已选择 {count} 张图片")
        self.audit_btn.setEnabled(count > 0)

    def _on_audit(self):
        """开始审核 - 自动判断单图或批量"""
        image_paths = self.image_drop.get_image_paths()
        if not image_paths:
            return

        brand_id = self.brand_combo.currentData()

        # 获取用户选择的压缩预设
        compression_preset = ["balanced", "high_quality", "high_compression", "no_compression"][self.compression_combo.currentIndex()]
        audit_service.set_compression_preset(compression_preset)

        if len(image_paths) == 1:
            # 单图审核
            self._start_single_audit(image_paths[0], brand_id, compression_preset)
        else:
            # 批量审核
            self._start_batch_audit(image_paths, brand_id, compression_preset)

    def _start_single_audit(self, image_path: str, brand_id: str, compression_preset: str):
        """开始单图审核"""
        logger.info(f"单图审核使用压缩预设: {compression_preset}")

        # 发送任务开始信号
        self.task_started.emit("单图审核")
        self.progress_updated.emit(-1, "正在预处理图片...", f"开始审核: {Path(image_path).name}")

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.status_label.setText("正在审核（可能需要1-2分钟）...")
        self.audit_btn.setEnabled(False)

        # 开始流式输出
        self.streaming_display.start_streaming("正在调用AI分析...")

        # 后台任务
        self._current_mode = "single"
        self.worker = Worker(self._run_audit_stream, image_path, brand_id)
        self.worker.finished_signal.connect(self._on_audit_finished)
        self.worker.error_signal.connect(self._on_audit_error)
        self.worker.progress_signal.connect(lambda p, m: self.progress_updated.emit(-1, m, m))
        self.worker.start()

    def _start_batch_audit(self, image_paths: list, brand_id: str, compression_preset: str):
        """开始批量审核"""
        logger.info(f"批量审核使用压缩预设: {compression_preset}")

        # 发送任务开始信号
        self.task_started.emit("批量审核")
        self.progress_updated.emit(0, f"准备审核 {len(image_paths)} 张图片...", f"开始批量审核，共 {len(image_paths)} 张图片")

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(image_paths))
        self.progress_bar.setValue(0)
        self.status_label.setText("正在批量审核...")
        self.audit_btn.setEnabled(False)

        # 开始流式输出
        self.streaming_display.start_streaming(f"正在批量审核 {len(image_paths)} 张图片...")

        # 保存设置
        self._total_images = len(image_paths)
        self._current_mode = "batch"
        self._batch_results = []

        # 连接流式结果信号
        self.streaming_result.connect(self._on_streaming_result)

        # 后台任务
        self._batch_worker = Worker(self._run_batch_audit, image_paths, brand_id)
        self._batch_worker.finished_signal.connect(self._on_batch_finished)
        self._batch_worker.error_signal.connect(self._on_audit_error)
        self._batch_worker.progress_signal.connect(self._on_batch_progress)
        self._batch_worker.start()

    def _run_audit_stream(self, image_path: str, brand_id: str, progress_callback=None):
        """执行流式审核"""
        from src.services.llm_service import llm_service

        self.progress_updated.emit(-1, "正在调用AI分析...", "图片预处理完成")

        # 预处理图片
        file_path = Path(image_path)
        with open(file_path, "rb") as f:
            image_data = f.read()

        image_format = file_path.suffix.lstrip(".").lower()
        if image_format == "jpg":
            image_format = "jpeg"

        image_base64, image_format = audit_service.preprocess_image(image_data, image_format)

        # 获取品牌规范规则清单
        rules_checklist = rules_context.get_rules_checklist(brand_id)

        # 流式调用LLM
        full_content = ""

        def stream_callback(text_chunk):
            nonlocal full_content
            full_content += text_chunk
            # 使用 QMetaObject.invokeMethod 在主线程更新UI
            QMetaObject.invokeMethod(
                self.streaming_display,
                "append_text",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, text_chunk)
            )

        try:
            for _ in llm_service.audit_image_stream(
                image_base64=image_base64,
                image_format=image_format,
                rules_checklist=rules_checklist,
                stream_callback=stream_callback,
            ):
                pass  # 迭代以完成流式输出

            self.progress_updated.emit(80, "正在生成报告...", "AI分析完成")

            # 停止流式显示并格式化JSON
            QMetaObject.invokeMethod(
                self.streaming_display,
                "stop_streaming",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, "解析结果中...")
            )

            # 解析结果
            result = llm_service.parse_stream_result(full_content)

            # 构建 AuditReport
            report = audit_service._build_report(result, rules_checklist)

            return report

        except Exception as e:
            logger.error(f"流式审核失败: {e}")
            raise

    def _run_batch_audit(self, image_paths: list, brand_id: str, progress_callback=None):
        """执行批量审核 - 使用合并请求，流式输出JSON"""
        import time

        logger.info(f"开始批量审核，共 {len(image_paths)} 张图片")

        total = len(image_paths)
        self._batch_results = []
        self._accumulated_md = ""  # 累积的MD格式结果

        def progress_cb(completed, total, message):
            """进度回调包装"""
            if progress_callback:
                progress_callback(completed, message)
            percent = int(completed / total * 100) if total > 0 else 0
            self.progress_updated.emit(percent, message, message)

        def stream_cb(text_chunk):
            """流式文本回调 - 实时显示JSON"""
            # 使用 QMetaObject.invokeMethod 确保在主线程更新UI
            QMetaObject.invokeMethod(
                self.streaming_display,
                "append_text",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, text_chunk)
            )

        def result_cb(result, index, completed, total):
            """最终结果回调 - 转换为MD格式并累积显示"""
            if result.get("status") == "success":
                report = result["report"]
                formatted = {
                    "file_name": result["file_name"],
                    "status": report.status.value,
                    "score": report.score,
                    "report": json.loads(report.to_json()),
                    "_index": completed  # 添加索引用于显示
                }
            else:
                formatted = {
                    "file_name": result["file_name"],
                    "status": "error",
                    "error": result.get("error", "未知错误"),
                    "_index": completed
                }

            self._batch_results.append(formatted)

            # 格式化当前图片的MD结果
            lines = self._format_single_result(formatted)
            current_md = "\n".join(lines)

            # 累积结果
            if self._accumulated_md:
                self._accumulated_md += "\n\n" + current_md
            else:
                self._accumulated_md = current_md

            # 清空JSON流式显示，设置累积的MD结果
            QMetaObject.invokeMethod(
                self.streaming_display,
                "set_text",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, self._accumulated_md)
            )

        start_time = time.time()

        # 使用合并请求：单次API调用处理多张图片，流式输出JSON
        audit_service.batch_audit_merged(
            image_paths=image_paths,
            brand_id=brand_id,
            max_images_per_request=None,
            progress_callback=progress_cb,
            stream_callback=stream_cb,
            result_callback=result_cb,
        )

        elapsed = time.time() - start_time
        logger.info(f"批量审核完成，耗时: {elapsed:.1f}秒")

        return self._batch_results

    def _on_streaming_result(self, result: dict, index: int, completed: int, total: int):
        """处理流式结果 - 实时更新UI，显示详细内容"""
        # 更新进度条
        self.progress_bar.setValue(completed)

        # 格式化单个结果
        lines = self._format_single_result(result)
        new_content = "\n".join(lines)

        # 获取当前文本并追加（线程安全）
        current = self.streaming_display.get_text()
        if current and not current.endswith("\n\n"):
            current += "\n\n"

        # 使用 QMetaObject.invokeMethod 确保在主线程更新UI
        QMetaObject.invokeMethod(
            self.streaming_display,
            "set_text",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(str, current + new_content)
        )

    def _format_single_result(self, result: dict) -> list:
        """格式化单个审核结果 - 同步导出报告格式"""
        lines = []

        status_map = {"pass": "PASS", "warning": "REVIEW", "fail": "FAIL", "error": "ERROR"}
        status_label = status_map.get(result.get("status"), "?")
        file_name = result.get("file_name", "未知")

        lines.append(f"--- 图片 {result.get('_index', '?')}: {file_name} ---")
        lines.append(f"状态: [{status_label}]")

        report = result.get("report", {})
        if result.get("status") == "error":
            lines.append(f"错误: {result.get('error', '未知错误')}")
            return lines

        if report:
            # 显示分数
            score = report.get("score", 0)
            if score:
                lines.append(f"分数: {score}")

            # 显示规则检查清单 - 使用导出报告格式
            rule_checks = report.get("rule_checks", [])
            if rule_checks:
                lines.append("")

                # 按状态排序: fail > review > pass
                status_order = {"fail": 0, "review": 1, "pass": 2}
                sorted_checks = sorted(rule_checks, key=lambda x: status_order.get(x.get("status"), 3))

                for check in sorted_checks:
                    rule_id = check.get("rule_id", "")
                    rule_content = check.get("rule_content", "") or rule_id
                    check_status = check.get("status", "pass")
                    confidence = check.get("confidence", 0)
                    reference = check.get("reference", "")

                    # 状态标签
                    check_status_map = {"pass": "PASS", "fail": "FAIL", "review": "REVIEW"}
                    check_status_label = check_status_map.get(check_status, "?")

                    # 导出报告格式: [状态] Rule_ID : 规则内容 -->> 状态 >> 参考文档，置信度：0.XX；
                    lines.append(f"[{check_status_label}] {rule_id} : {rule_content} -->> {check_status_label} >> {reference}，置信度：{confidence:.2f}；")

        return lines

    def _on_batch_progress(self, current: int, message: str):
        """批量审核进度"""
        self.progress_bar.setValue(current)
        self.status_label.setText(message)
        if hasattr(self, '_total_images') and self._total_images > 0:
            percent = int(current / self._total_images * 100)
            self.progress_updated.emit(percent, message, message)

    def _on_audit_finished(self, report):
        """单图审核完成"""
        self.audit_result = report

        self.progress_bar.setVisible(False)
        self.status_label.setText("审核完成!")
        self.audit_btn.setEnabled(True)

        self.streaming_display.set_export_enabled(True)
        self.streaming_display.show_expand_button(False)  # 单图审核隐藏展开按钮

        # 停止流式显示（不自动转换，使用报告数据更新显示）
        self.streaming_display._is_streaming = False
        self.streaming_display.status_label.setText("审核完成")

        # 使用报告数据生成HTML表格显示
        report_dict = json.loads(report.to_json())
        html = self.streaming_display._audit_to_html(report_dict)
        text = self.streaming_display._audit_to_text(report_dict)
        self.streaming_display.set_html(html, text)

        # 发送任务完成信号
        grade_map = {'pass': 'PASS', 'review': 'REVIEW', 'fail': 'FAIL'}
        grade = grade_map.get(report.status.value, 'REVIEW')
        self.task_finished.emit(True, f"审核完成，结果: {grade}")

        # 保存到历史
        self._save_single_to_history(report)

    def _on_batch_finished(self, results: list):
        """批量审核完成"""
        # 断开信号
        try:
            self.streaming_result.disconnect(self._on_streaming_result)
        except:
            pass

        self.progress_bar.setVisible(False)
        self.audit_btn.setEnabled(True)

        # 计算摘要 - 支持 pass/review/fail 状态
        total = len(results)
        pass_count = len([r for r in results if r.get("status") == "pass"])
        review_count = len([r for r in results if r.get("status") in ("review", "warning")])
        fail_count = len([r for r in results if r.get("status") == "fail"])
        error_count = len([r for r in results if r.get("status") == "error"])

        # 计算整体状态：fail > review > pass
        if fail_count > 0 or error_count > 0:
            overall_status = "FAIL"
        elif review_count > 0:
            overall_status = "REVIEW"
        else:
            overall_status = "PASS"

        # 使用表格格式显示
        html_content = self._format_batch_results_html(
            results, total, pass_count, review_count, fail_count, error_count, overall_status
        )

        # 生成纯文本版本用于复制
        text_content = self._format_batch_results_text(
            results, total, pass_count, review_count, fail_count, error_count, overall_status
        )

        self.streaming_display.set_html(html_content, text_content)
        self.streaming_display.status_label.setText("批量审核完成")
        self.streaming_display._is_streaming = False

        # 存储批量数据并显示展开按钮
        batch_data = {
            "results": results,
            "summary": {
                "total": total,
                "pass_count": pass_count,
                "review_count": review_count,
                "fail_count": fail_count
            },
            "status": overall_status.lower()
        }
        self.streaming_display.set_batch_data(batch_data, html_content, text_content)
        self.streaming_display.show_expand_button(True)

        self.status_label.setText("批量审核完成!")

        self.streaming_display.set_export_enabled(True)

        # 发送任务完成信号
        self.task_finished.emit(True, f"批量审核完成，共 {total} 张")

        # 保存批量结果
        self._last_batch_results = results
        self._save_batch_to_history(results, overall_status.lower())

    def _format_batch_results_html(self, results: list, total: int, pass_count: int,
                                     warning_count: int, fail_count: int, error_count: int,
                                     overall_status: str) -> str:
        """将批量审核结果格式化为HTML表格"""

        # 状态颜色映射
        status_colors = {
            "pass": "#28a745",
            "warning": "#ffc107",
            "fail": "#dc3545",
            "error": "#6c757d"
        }

        status_labels = {
            "pass": "PASS",
            "warning": "REVIEW",
            "fail": "FAIL",
            "error": "ERROR"
        }

        overall_color = status_colors.get(overall_status.lower(), "#6c757d")

        html_parts = [
            '<!DOCTYPE html>',
            '<html><head>',
            '<meta charset="utf-8">',
            '<style>',
            'html, body { font-family: "Microsoft YaHei", sans-serif; font-size: 13px; margin: 0; padding: 0; width: 100%; height: auto; }',
            'body { display: block; box-sizing: border-box; }',
            '.summary { background: #f8f9fa; padding: 12px; border-radius: 6px; margin-bottom: 16px; width: 100%; box-sizing: border-box; }',
            '.summary-title { font-weight: bold; font-size: 14px; margin-bottom: 8px; }',
            '.summary-stats { display: inline-block; margin-right: 20px; }',
            '.overall-status { font-weight: bold; padding: 4px 12px; border-radius: 4px; color: white; }',
            'table { width: 100%; border-collapse: collapse; margin-top: 10px; table-layout: auto; }',
            'th { background: #e9ecef; padding: 10px 8px; text-align: left; font-weight: bold; border-bottom: 2px solid #dee2e6; }',
            'td { padding: 8px; border-bottom: 1px solid #dee2e6; vertical-align: top; }',
            'tr:hover { background: #f8f9fa; }',
            '.status-badge { padding: 2px 8px; border-radius: 3px; font-weight: bold; font-size: 11px; }',
            '.status-pass { background: #d4edda; color: #155724; }',
            '.status-review { background: #fff3cd; color: #856404; }',
            '.status-fail { background: #f8d7da; color: #721c24; }',
            '.status-error { background: #e2e3e5; color: #383d41; }',
            '.rule-pass { color: #28a745; }',
            '.rule-fail { color: #dc3545; font-weight: bold; }',
            '.rule-review { color: #856404; }',
            '.file-name { font-weight: bold; color: #333; }',
            '.score { font-weight: bold; font-size: 14px; }',
            '.rule-table { width: 100%; font-size: 12px; margin-top: 4px; }',
            '.rule-table td { padding: 3px 4px; border: none; }',
            '.rule-id { color: #666; width: 60px; }',
            '.rule-content { color: #333; }',
            '.rule-confidence { color: #888; width: 50px; text-align: right; }',
            '</style>',
            '</head><body>',
        ]

        # 摘要部分
        html_parts.append('<div class="summary">')
        html_parts.append('<div class="summary-title">【批量审核摘要】</div>')
        html_parts.append(f'<span class="summary-stats">总数: {total}</span>')
        html_parts.append(f'<span class="summary-stats" style="color:#28a745;">PASS: {pass_count}</span>')
        html_parts.append(f'<span class="summary-stats" style="color:#856404;">REVIEW: {warning_count}</span>')
        html_parts.append(f'<span class="summary-stats" style="color:#dc3545;">FAIL: {fail_count}</span>')
        if error_count > 0:
            html_parts.append(f'<span class="summary-stats" style="color:#6c757d;">ERROR: {error_count}</span>')
        html_parts.append(f'<br><br>整体状态: <span class="overall-status" style="background:{overall_color};">{overall_status}</span>')
        html_parts.append('</div>')

        # 详细结果表格
        html_parts.append('<div class="summary-title">【详细结果】</div>')
        html_parts.append('<table>')
        html_parts.append('<tr><th style="width:30px;">#</th><th style="width:150px;">文件名</th>'
                         '<th style="width:60px;">状态</th><th style="width:50px;">分数</th>'
                         '<th>规则检查 (FAIL/REVIEW)</th></tr>')

        for i, result in enumerate(results, 1):
            status = result.get("status", "error")
            status_label = status_labels.get(status, "?")
            # 统一 warning 为 review
            display_status = "review" if status == "warning" else status
            status_class = f"status-{display_status}"
            file_name = result.get("file_name", "未知")

            # 获取报告数据
            report = result.get("report", {})
            score = report.get("score", 0) if report else 0

            # 构建规则检查摘要（只显示FAIL和REVIEW的数量）
            rule_checks = report.get("rule_checks", []) if report else []
            fail_count_item = len([c for c in rule_checks if c.get("status") == "fail"])
            review_count_item = len([c for c in rule_checks if c.get("status") in ("review", "warning")])

            rule_summary_parts = []

            if fail_count_item > 0:
                rule_summary_parts.append(f'<span style="color:#dc3545;font-weight:bold;">FAIL: {fail_count_item}</span>')
            if review_count_item > 0:
                rule_summary_parts.append(f'<span style="color:#856404;">REVIEW: {review_count_item}</span>')
            if not rule_summary_parts:
                rule_summary_parts.append('<span style="color:#28a745;">全部通过</span>')

            rule_summary = ' | '.join(rule_summary_parts)

            html_parts.append(f'<tr>')
            html_parts.append(f'<td>{i}</td>')
            html_parts.append(f'<td class="file-name">{file_name}</td>')
            html_parts.append(f'<td><span class="status-badge {status_class}">{status_label}</span></td>')
            html_parts.append(f'<td class="score">{score}</td>')
            html_parts.append(f'<td>{rule_summary}</td>')
            html_parts.append(f'</tr>')

        html_parts.append('</table>')
        html_parts.append('</body></html>')

        return ''.join(html_parts)

    def _format_batch_results_text(self, results: list, total: int, pass_count: int,
                                    review_count: int, fail_count: int, error_count: int,
                                    overall_status: str) -> str:
        """将批量审核结果格式化为纯文本"""
        lines = []

        # 状态映射
        status_labels = {
            "pass": "PASS",
            "warning": "REVIEW",
            "fail": "FAIL",
            "error": "ERROR"
        }

        # 添加摘要
        lines.append("【批量审核摘要】")
        lines.append(f"总数: {total}")
        lines.append(f"PASS: {pass_count}")
        lines.append(f"REVIEW: {review_count}")
        lines.append(f"FAIL: {fail_count}")
        if error_count > 0:
            lines.append(f"ERROR: {error_count}")
        lines.append(f"整体状态: {overall_status}")
        lines.append("")

        # 添加详细结果
        lines.append("【详细结果】")
        lines.append("")

        for i, result in enumerate(results, 1):
            status = result.get("status", "error")
            status_label = status_labels.get(status, "?")
            file_name = result.get("file_name", "未知")

            lines.append(f"--- 图片 {i}: {file_name} ---")
            lines.append(f"状态: [{status_label}]")

            report = result.get("report", {})
            if result.get("status") == "error":
                lines.append(f"错误: {result.get('error', '未知错误')}")
                lines.append("")
                continue

            if report:
                score = report.get("score", 0)
                lines.append(f"分数: {score}")

                # 显示规则检查清单
                rule_checks = report.get("rule_checks", [])
                if rule_checks:
                    lines.append("")

                    # 按状态排序: fail > review > pass
                    status_order = {"fail": 0, "review": 1, "pass": 2}
                    sorted_checks = sorted(rule_checks, key=lambda x: status_order.get(x.get("status"), 3))

                    for check in sorted_checks:
                        rule_id = check.get("rule_id", "")
                        rule_content = check.get("rule_content", "") or rule_id
                        check_status = check.get("status", "pass")
                        confidence = check.get("confidence", 0)
                        reference = check.get("reference", "")

                        check_status_map = {"pass": "PASS", "fail": "FAIL", "review": "REVIEW"}
                        check_status_label = check_status_map.get(check_status, "?")

                        lines.append(f"[{check_status_label}] {rule_id} : {rule_content} -->> {check_status_label} >> {reference}，置信度：{confidence:.2f}；")

            lines.append("")

        return '\n'.join(lines)

    def _on_audit_error(self, error: str):
        """审核出错"""
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"审核失败: {error}")
        self.audit_btn.setEnabled(True)

        # 发送任务失败信号
        self.task_finished.emit(False, f"审核失败: {error}")

        InfoBar.error(
            title="错误",
            content=f"审核失败:\n{error}",
            position=InfoBarPosition.TOP,
            duration=5000,
            parent=self
        )

    def _save_single_to_history(self, report):
        """保存单图审核结果到历史"""
        history_dir = get_app_dir() / "data" / "audit_history"
        history_dir.mkdir(parents=True, exist_ok=True)

        batch_id = f"single_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        image_paths = self.image_drop.get_image_paths()
        file_name = Path(image_paths[0]).name if image_paths else ""

        history_data = {
            "batch_id": batch_id,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "brand_name": self.brand_combo.currentText(),
            "file_name": file_name,
            "file_count": 1,
            "status": report.status.value,
            "score": report.score,
            "report": json.loads(report.to_json())
        }

        # 保存报告文件
        report_file = history_dir / f"{batch_id}.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(history_data, f, ensure_ascii=False, indent=2)

        # 更新历史索引
        self._update_history_index(history_data)

    def _save_batch_to_history(self, results: list, overall_status: str = None):
        """保存批量审核结果到历史"""
        history_dir = get_app_dir() / "data" / "audit_history"
        history_dir.mkdir(parents=True, exist_ok=True)

        batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        # 统计状态 - 统一使用 pass/review/fail
        pass_count = len([r for r in results if r.get("status") == "pass"])
        review_count = len([r for r in results if r.get("status") in ("review", "warning")])
        fail_count = len([r for r in results if r.get("status") == "fail"])

        # 计算整体状态：fail > review > pass
        if overall_status is None:
            if fail_count > 0:
                overall_status = "fail"
            elif review_count > 0:
                overall_status = "review"
            else:
                overall_status = "pass"

        history_data = {
            "batch_id": batch_id,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "brand_name": self.brand_combo.currentText(),
            "file_count": len(results),
            "status": overall_status,
            "summary": {
                "total": len(results),
                "pass_count": pass_count,
                "review_count": review_count,  # 使用 review_count 而非 warning_count
                "fail_count": fail_count
            },
            "results": results
        }

        report_file = history_dir / f"{batch_id}.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(history_data, f, ensure_ascii=False, indent=2)

        self._update_history_index(history_data, is_batch=True)

    def _update_history_index(self, history_data: dict, is_batch: bool = False):
        """更新历史索引"""
        history_dir = get_app_dir() / "data" / "audit_history"
        index_file = history_dir / "history_index.json"
        history_list = []
        if index_file.exists():
            with open(index_file, "r", encoding="utf-8") as f:
                history_list = json.load(f)

        # 统一状态值为 pass/review/fail
        status = history_data.get("status", "review")
        if status == "warning":
            status = "review"

        entry = {
            "batch_id": history_data["batch_id"],
            "time": history_data["time"],
            "brand_name": history_data["brand_name"],
            "file_count": history_data.get("file_count", 1),
            "status": status,
        }

        if is_batch:
            summary = history_data.get("summary", {})
            pass_count = summary.get("pass_count", 0)
            review_count = summary.get("review_count", summary.get("warning_count", 0))
            fail_count = summary.get("fail_count", 0)
            # 根据整体状态确定等级：fail > review > pass
            batch_status = history_data.get("status", "fail")
            if batch_status == "warning":
                batch_status = "review"
            grade_map = {'pass': 'PASS', 'review': 'REVIEW', 'fail': 'FAIL'}
            entry["grade"] = grade_map.get(batch_status, "REVIEW")
        else:
            # 单图审核
            status = history_data.get("status", "review")
            if status == "warning":
                status = "review"
            grade_map = {'pass': 'PASS', 'review': 'REVIEW', 'fail': 'FAIL'}
            entry["grade"] = grade_map.get(status, "REVIEW")
            entry["score"] = history_data.get("score", 0)

        history_list.insert(0, entry)
        history_list = history_list[:100]

        with open(index_file, "w", encoding="utf-8") as f:
            json.dump(history_list, f, ensure_ascii=False, indent=2)

    def _on_export_json(self):
        """导出JSON报告"""
        if getattr(self, '_current_mode', None) == "batch" and hasattr(self, '_last_batch_results'):
            self._export_batch_json()
        elif self.audit_result:
            self._export_single_json(self.audit_result)
        else:
            InfoBar.warning(title="提示", content="没有可导出的报告", parent=self)

    def _on_export_md(self):
        """导出Markdown报告"""
        if getattr(self, '_current_mode', None) == "batch" and hasattr(self, '_last_batch_results'):
            self._export_batch_md()
        elif self.audit_result:
            self._export_single_md(self.audit_result)
        else:
            InfoBar.warning(title="提示", content="没有可导出的报告", parent=self)

    def _export_single_json(self, report):
        """导出单图JSON"""
        export_dir = get_app_dir() / "data" / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出JSON报告",
            str(export_dir / f"audit_report_{timestamp}.json"),
            "JSON文件 (*.json)"
        )
        if file_path:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(report.to_json())
            InfoBar.success(title="成功", content=f"已导出到:\n{file_path}", parent=self)

    def _export_single_md(self, report):
        """导出单图Markdown"""
        export_dir = get_app_dir() / "data" / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出Markdown报告",
            str(export_dir / f"audit_report_{timestamp}.md"),
            "Markdown文件 (*.md)"
        )
        if file_path:
            md_content = self._report_to_markdown(report)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(md_content)
            InfoBar.success(title="成功", content=f"已导出到:\n{file_path}", parent=self)

    def _export_batch_json(self):
        """导出批量JSON"""
        export_dir = get_app_dir() / "data" / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出批量JSON报告",
            str(export_dir / f"batch_report_{timestamp}.json"),
            "JSON文件 (*.json)"
        )
        if file_path:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "results": self._last_batch_results
                }, f, ensure_ascii=False, indent=2)
            InfoBar.success(title="成功", content=f"已导出到:\n{file_path}", parent=self)

    def _export_batch_md(self):
        """导出批量Markdown"""
        export_dir = get_app_dir() / "data" / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出批量Markdown报告",
            str(export_dir / f"batch_report_{timestamp}.md"),
            "Markdown文件 (*.md)"
        )
        if file_path:
            md_content = self._generate_batch_markdown()
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(md_content)
            InfoBar.success(title="成功", content=f"已导出到:\n{file_path}", parent=self)

    def _report_to_markdown(self, report) -> str:
        """将报告转换为Markdown"""
        lines = [
            "# 品牌合规审核报告",
            "",
            f"**分数**: {report.score}",
            "",
        ]

        if hasattr(report, 'rule_checks') and report.rule_checks:
            lines.append("## 规则检查清单")
            lines.append("")

            status_order = {"fail": 0, "review": 1, "pass": 2}
            sorted_checks = sorted(report.rule_checks, key=lambda x: status_order.get(x.status, 3))

            for check in sorted_checks:
                status_text = {"pass": "[PASS]", "fail": "[FAIL]", "review": "[REVIEW]"}.get(check.status, "[?]")
                lines.append(f"- {status_text} {check.rule_id}: {check.rule_content}")
                lines.append(f"  - 置信度: {check.confidence:.0%}")
                if check.detail:
                    lines.append(f"  - 说明: {check.detail}")

        return "\n".join(lines)

    def _generate_batch_markdown(self) -> str:
        """生成批量报告Markdown"""
        lines = [
            "# 批量审核报告",
            f"\n**生成时间:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
            "---\n"
        ]

        for i, result in enumerate(self._last_batch_results, 1):
            status_map = {"pass": "PASS", "warning": "REVIEW", "fail": "FAIL", "error": "ERROR"}
            status_label = status_map.get(result.get("status"), "?")
            lines.append(f"## {i}. {result.get('file_name', '未知文件')}")
            lines.append(f"\n**状态:** {status_label}\n")

            report = result.get("report", {})
            if report:
                rule_checks = report.get("rule_checks", [])
                if rule_checks:
                    lines.append("### 规则检查清单\n")
                    for check in rule_checks:
                        status_text = {"pass": "[PASS]", "fail": "[FAIL]", "review": "[REVIEW]"}.get(check.get("status"), "[?]")
                        lines.append(f"- {status_text} {check.get('rule_id', '')}: {check.get('rule_content', '')}")
                    lines.append("")

            lines.append("---\n")

        return "\n".join(lines)