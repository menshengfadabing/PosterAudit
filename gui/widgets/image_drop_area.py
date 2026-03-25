"""图片拖拽区域组件（Fluent风格）"""

from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFileDialog, QFrame
from PySide6.QtGui import QPixmap

from qfluentwidgets import (
    PushButton, PrimaryPushButton, StrongBodyLabel,
    CaptionLabel, CardWidget, FluentIcon as FIF
)


class ImageDropArea(CardWidget):
    """图片拖拽上传区域 - Fluent风格"""

    image_selected = Signal(str)
    images_selected = Signal(list)

    def __init__(self, parent=None, multi_select: bool = False, max_images: int = 10):
        super().__init__(parent)
        self.multi_select = multi_select
        self.max_images = max_images
        self.image_paths: list[str] = []
        self._init_ui()

    def _init_ui(self):
        self.setAcceptDrops(True)
        self.setMinimumSize(350, 220)
        self.setBorderRadius(8)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # 拖拽提示区域
        self.drop_frame = QFrame()
        self.drop_frame.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Sunken)
        self.drop_frame.setStyleSheet("""
            QFrame {
                border: 2px dashed #aaa;
                border-radius: 8px;
                background-color: rgba(0, 0, 0, 0.02);
            }
            QFrame:hover {
                border-color: #0078d4;
                background-color: rgba(0, 120, 212, 0.05);
            }
        """)

        drop_layout = QVBoxLayout(self.drop_frame)
        drop_layout.setSpacing(8)

        self.hint_label = StrongBodyLabel("拖拽图片到此处\n或点击选择图片")
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_layout.addWidget(self.hint_label)

        self.format_label = CaptionLabel("支持格式: PNG, JPG, JPEG, BMP, WEBP")
        self.format_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_layout.addWidget(self.format_label)

        layout.addWidget(self.drop_frame)

        # 按钮区域
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.select_btn = PrimaryPushButton("选择图片")
        self.select_btn.clicked.connect(self._on_select_clicked)
        btn_layout.addWidget(self.select_btn)

        self.clear_btn = PushButton("清空")
        self.clear_btn.clicked.connect(self.clear_images)
        self.clear_btn.setVisible(False)
        btn_layout.addWidget(self.clear_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            for url in urls:
                if self._is_image_file(url.toLocalFile()):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        files = []
        urls = event.mimeData().urls()

        for url in urls:
            file_path = url.toLocalFile()
            if self._is_image_file(file_path):
                files.append(file_path)

        if files:
            if self.multi_select:
                self._add_images(files)
            else:
                self._set_image(files[0])

    def _on_select_clicked(self):
        file_filter = "图片文件 (*.png *.jpg *.jpeg *.bmp *.webp *.gif)"
        if self.multi_select:
            files, _ = QFileDialog.getOpenFileNames(self, "选择图片", "", file_filter)
            if files:
                self._add_images(files[:self.max_images - len(self.image_paths)])
        else:
            file_path, _ = QFileDialog.getOpenFileName(self, "选择图片", "", file_filter)
            if file_path:
                self._set_image(file_path)

    def _is_image_file(self, file_path: str) -> bool:
        ext = Path(file_path).suffix.lower()
        return ext in {'.png', '.jpg', '.jpeg', '.bmp', '.webp', '.gif'}

    def _set_image(self, file_path: str):
        self.image_paths = [file_path]
        self.hint_label.setText(Path(file_path).name)
        self.clear_btn.setVisible(True)
        self.image_selected.emit(file_path)

    def _add_images(self, file_paths: list):
        for path in file_paths:
            if path not in self.image_paths:
                self.image_paths.append(path)
                if len(self.image_paths) >= self.max_images:
                    break

        self.hint_label.setText(f"已选择 {len(self.image_paths)} 张图片")
        self.clear_btn.setVisible(True)
        self.images_selected.emit(self.image_paths)

    def clear_images(self):
        self.image_paths.clear()
        self.hint_label.setText("拖拽图片到此处\n或点击选择图片")
        self.clear_btn.setVisible(False)

    def get_image_paths(self) -> list[str]:
        return self.image_paths.copy()

    def get_first_image(self) -> str | None:
        return self.image_paths[0] if self.image_paths else None