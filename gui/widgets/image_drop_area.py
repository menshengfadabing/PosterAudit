"""图片拖拽区域组件"""

from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QFileDialog, QFrame
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap


class ImageDropArea(QWidget):
    """图片拖拽上传区域"""

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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)

        # 拖拽提示区域
        self.drop_frame = QFrame()
        self.drop_frame.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Sunken)
        self.drop_frame.setStyleSheet("""
            QFrame {
                border: 2px dashed #aaa;
                border-radius: 10px;
                background-color: #f9f9f9;
            }
            QFrame:hover {
                border-color: #4a9eff;
                background-color: #f0f7ff;
            }
        """)

        drop_layout = QVBoxLayout(self.drop_frame)

        self.hint_label = QLabel("拖拽图片到此处\n或点击选择图片")
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint_label.setStyleSheet("color: #666; font-size: 16px;")
        drop_layout.addWidget(self.hint_label)

        self.format_label = QLabel("支持格式: PNG, JPG, JPEG, BMP, WEBP")
        self.format_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.format_label.setStyleSheet("color: #999; font-size: 13px;")
        drop_layout.addWidget(self.format_label)

        layout.addWidget(self.drop_frame)

        # 按钮区域
        btn_layout = QVBoxLayout()

        self.select_btn = QPushButton("选择图片")
        self.select_btn.setStyleSheet("font-size: 15px; padding: 10px;")
        self.select_btn.clicked.connect(self._on_select_clicked)

        self.clear_btn = QPushButton("清空")
        self.clear_btn.setStyleSheet("font-size: 15px; padding: 10px;")
        self.clear_btn.clicked.connect(self.clear_images)
        self.clear_btn.setVisible(False)

        btn_row = QVBoxLayout()
        btn_row.addWidget(self.select_btn)
        btn_row.addWidget(self.clear_btn)

        layout.addLayout(btn_row)

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