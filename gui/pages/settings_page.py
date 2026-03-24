"""设置页面 - 配置API和品牌规范"""

import json
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QGroupBox, QFileDialog, QMessageBox, QTextEdit, QComboBox
)
from PySide6.QtCore import Qt

from src.utils.config import settings, get_app_dir
from src.services.llm_service import llm_service
from src.services.rules_context import rules_context
from src.services.document_parser import document_parser


class SettingsPage(QWidget):
    """设置页面"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self._load_settings()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # 标题
        title = QLabel("设置")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(title)

        # API配置
        api_group = QGroupBox("API配置")
        api_layout = QVBoxLayout(api_group)

        # API Key
        key_layout = QHBoxLayout()
        key_layout.addWidget(QLabel("API Key:"))
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("输入API密钥...")
        key_layout.addWidget(self.api_key_edit)
        api_layout.addLayout(key_layout)

        # API Base
        base_layout = QHBoxLayout()
        base_layout.addWidget(QLabel("API地址:"))
        self.api_base_edit = QLineEdit()
        self.api_base_edit.setText(settings.openai_api_base)
        base_layout.addWidget(self.api_base_edit)
        api_layout.addLayout(base_layout)

        # Model
        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("模型:"))
        self.model_edit = QLineEdit()
        self.model_edit.setText(settings.doubao_model)
        model_layout.addWidget(self.model_edit)
        api_layout.addLayout(model_layout)

        # 保存按钮
        save_api_btn = QPushButton("保存API配置")
        save_api_btn.clicked.connect(self._save_api_config)
        save_api_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                padding: 8px 20px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        api_layout.addWidget(save_api_btn)

        layout.addWidget(api_group)

        # 品牌规范管理
        rules_group = QGroupBox("品牌规范管理")
        rules_layout = QVBoxLayout(rules_group)

        # 规范选择
        select_layout = QHBoxLayout()
        select_layout.addWidget(QLabel("当前规范:"))
        self.rules_combo = QComboBox()
        self.rules_combo.setMinimumWidth(200)
        select_layout.addWidget(self.rules_combo)

        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self._load_rules_list)
        select_layout.addWidget(refresh_btn)

        rules_layout.addLayout(select_layout)

        # 上传规范文档
        upload_layout = QHBoxLayout()
        self.upload_btn = QPushButton("上传规范文档 (PDF/PPT)")
        self.upload_btn.clicked.connect(self._upload_document)
        upload_layout.addWidget(self.upload_btn)

        self.new_btn = QPushButton("新建空白规范")
        self.new_btn.clicked.connect(self._new_rules)
        upload_layout.addWidget(self.new_btn)

        rules_layout.addLayout(upload_layout)

        # 规范预览
        self.rules_preview = QTextEdit()
        self.rules_preview.setReadOnly(True)
        self.rules_preview.setMaximumHeight(200)
        self.rules_preview.setPlaceholderText("选择或上传品牌规范后预览...")
        rules_layout.addWidget(self.rules_preview)

        # 删除按钮
        self.delete_btn = QPushButton("删除当前规范")
        self.delete_btn.clicked.connect(self._delete_rules)
        self.delete_btn.setStyleSheet("background-color: #e74c3c; color: white;")
        rules_layout.addWidget(self.delete_btn)

        layout.addWidget(rules_group)

        # 缓存设置
        cache_group = QGroupBox("缓存设置")
        cache_layout = QVBoxLayout(cache_group)

        cache_info = QLabel("审核结果缓存可加速重复图片的审核速度")
        cache_layout.addWidget(cache_info)

        clear_cache_btn = QPushButton("清空缓存")
        clear_cache_btn.clicked.connect(self._clear_cache)
        cache_layout.addWidget(clear_cache_btn)

        layout.addWidget(cache_group)

        layout.addStretch()

        # 加载规范列表
        self._load_rules_list()

    def _load_settings(self):
        """加载设置"""
        self.api_key_edit.setText(settings.openai_api_key)
        self.api_base_edit.setText(settings.openai_api_base)
        self.model_edit.setText(settings.doubao_model)

    def _save_api_config(self):
        """保存API配置"""
        api_key = self.api_key_edit.text().strip()
        api_base = self.api_base_edit.text().strip()
        model = self.model_edit.text().strip()

        if not api_key:
            QMessageBox.warning(self, "警告", "请输入API Key")
            return

        # 更新配置
        llm_service.set_api_config(api_key, api_base, model)

        # 保存到.env文件
        env_path = get_app_dir() / ".env"
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(f"OPENAI_API_KEY={api_key}\n")
            f.write(f"OPENAI_API_BASE={api_base}\n")
            f.write(f"DOUBAO_MODEL={model}\n")

        QMessageBox.information(self, "成功", "API配置已保存")

    def _load_rules_list(self):
        """加载规范列表"""
        self.rules_combo.clear()

        rules_list = rules_context.list_rules()
        for rule in rules_list:
            brand_id = rule.get("brand_id", "")
            brand_name = rule.get("brand_name", "未命名")
            self.rules_combo.addItem(f"{brand_name} ({brand_id})", brand_id)

        if self.rules_combo.count() == 0:
            self.rules_combo.addItem("暂无规范", "")

        self._on_rules_changed()

    def _on_rules_changed(self):
        """规范选择变化"""
        brand_id = self.rules_combo.currentData()
        if brand_id:
            rules = rules_context.get_rules(brand_id)
            if rules:
                self.rules_preview.setPlainText(rules.to_json())
            rules_context.set_current_brand(brand_id)
        else:
            self.rules_preview.clear()

    def _upload_document(self):
        """上传规范文档"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择规范文档", "",
            "支持的文件 (*.pdf *.pptx *.ppt);;所有文件 (*.*)"
        )

        if not file_path:
            return

        try:
            # 解析文档
            rules = document_parser.parse_file(file_path)

            # 保存
            brand_id = rules_context.add_rules(rules)

            QMessageBox.information(
                self, "成功",
                f"规范文档已解析并保存\n品牌: {rules.brand_name}\nID: {brand_id}"
            )

            self._load_rules_list()

        except Exception as e:
            QMessageBox.critical(self, "错误", f"解析失败: {str(e)}")

    def _new_rules(self):
        """新建空白规范"""
        from src.models.schemas import BrandRules

        rules = BrandRules(
            brand_id="",
            brand_name="新品牌",
            version="1.0",
        )

        brand_id = rules_context.add_rules(rules)

        QMessageBox.information(self, "成功", f"已创建空白规范: {brand_id}")
        self._load_rules_list()

    def _delete_rules(self):
        """删除规范"""
        brand_id = self.rules_combo.currentData()
        if not brand_id:
            QMessageBox.warning(self, "警告", "请选择要删除的规范")
            return

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除规范 '{self.rules_combo.currentText()}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            rules_context.delete_rules(brand_id)
            self._load_rules_list()
            QMessageBox.information(self, "成功", "规范已删除")

    def _clear_cache(self):
        """清空缓存"""
        from src.services.llm_service import audit_cache
        audit_cache.clear()
        QMessageBox.information(self, "成功", "缓存已清空")