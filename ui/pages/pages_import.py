from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QCheckBox, QMessageBox, QSizePolicy,
    QAbstractItemView, QFileDialog
)
from PySide6.QtCore import Qt, QSize

from logger import logger
from spider.index_manage import IndexManager
from importer import preview_export, get_post_integrity, import_selected


class ImportItemWidget(QWidget):
    """导入列表中的单个帖子项"""

    def __init__(
        self,
        post_key: str,
        display_name: str,
        local_info: str = "",
        conflict: bool = False,
        valid: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.post_key = post_key
        self.display_name = display_name
        self.valid = valid

        layout = QHBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)

        self.checkbox = QCheckBox()
        self.checkbox.setEnabled(valid)
        layout.addWidget(self.checkbox)
        layout.addSpacing(8)

        self.name_label = QLabel(display_name)
        self.name_label.setStyleSheet(
            "font-size: 13px; font-style: italic;" if not valid else "font-size: 13px;"
        )
        self.name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.name_label)

        if local_info:
            info_label = QLabel(local_info)
            info_label.setStyleSheet(
                "font-size: 12px; font-weight: bold; color: #FFFFFF; padding: 0 8px;"
            )
            layout.addWidget(info_label)

        if not valid:
            badge = QLabel("数据不完整，无法导入")
            badge.setStyleSheet(
                "background-color: #dc3545; color: white; border-radius: 4px; "
                "padding: 2px 8px; font-size: 11px; font-weight: bold;"
            )
            layout.addWidget(badge)
        elif conflict:
            badge = QLabel("⛔ 已存在")
            badge.setStyleSheet(
                "background-color: #9b72cf; color: white; border-radius: 4px; "
                "padding: 2px 8px; font-size: 11px; font-weight: bold;"
            )
            layout.addWidget(badge)

        self.setLayout(layout)
        self.setFixedHeight(40)

    def is_checked(self) -> bool:
        return self.valid and self.checkbox.isChecked()

    def set_checked(self, checked: bool):
        if self.valid:
            self.checkbox.setChecked(checked)


class PageImport(QWidget):
    def __init__(self, main_window=None):
        super().__init__()
        self.main_window = main_window
        self.index_manager = IndexManager()
        self.export_data = None
        self.export_dir = None
        self.item_widgets: dict[str, ImportItemWidget] = {}
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        title = QLabel("【导入功能区】")
        title.setStyleSheet("font-weight: bold; font-size: 14px; color: #333333;")
        layout.addWidget(title)

        instructions = QLabel(
            "选择一个 TiebaShelf 导出文件夹（TiebaShelf_share_xxx），\n"
            "预览可导入的帖子后勾选要导入的帖子。已存在的帖子会提示合并。"
        )
        instructions.setStyleSheet("font-size: 13px; color: #555555; margin-bottom: 8px;")
        layout.addWidget(instructions)

        folder_layout = QHBoxLayout()

        self.open_btn = QPushButton("打开文件夹")
        self.open_btn.setFixedSize(100, 30)
        self.open_btn.clicked.connect(self.open_export_folder)
        folder_layout.addWidget(self.open_btn)

        self.folder_label = QLabel("未选择文件夹")
        self.folder_label.setStyleSheet("font-size: 12px; color: #888888;")
        folder_layout.addWidget(self.folder_label)

        folder_layout.addStretch()
        layout.addLayout(folder_layout)

        self.list_widget = QListWidget()
        self.list_widget.setObjectName('postsList')
        self.list_widget.setSelectionMode(QAbstractItemView.NoSelection)
        layout.addWidget(self.list_widget)

        bottom_bar = QWidget()
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(0, 4, 0, 0)

        self.import_btn = QPushButton("导入选中")
        self.import_btn.setEnabled(False)
        self.import_btn.clicked.connect(self.do_import)
        bottom_layout.addWidget(self.import_btn)

        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.setEnabled(False)
        self.select_all_btn.clicked.connect(self.select_all)
        bottom_layout.addWidget(self.select_all_btn)

        self.deselect_all_btn = QPushButton("取消全选")
        self.deselect_all_btn.setEnabled(False)
        self.deselect_all_btn.clicked.connect(self.deselect_all)
        bottom_layout.addWidget(self.deselect_all_btn)

        bottom_layout.addStretch()
        layout.addWidget(bottom_bar)

        self.setLayout(layout)

    def open_export_folder(self):
        self.reset_state()
        folder = QFileDialog.getExistingDirectory(self, "选择 TiebaShelf 导出文件夹")
        if not folder:
            return

        self.export_dir = Path(folder)

        data = preview_export(self.export_dir)
        if data is None:
            QMessageBox.warning(
                self, "导入失败",
                "所选文件夹不是有效的 TiebaShelf 导出文件夹\n（缺少 export.json 或格式错误）"
            )
            return

        self.export_data = data
        self.folder_label.setText(self.export_dir.name)
        self.populate_list(data)

    def _get_local_info(self, post_entry: dict) -> tuple[bool, str]:
        post_id = post_entry['post_id']
        see_lz = post_entry['see_lz']
        post_key = f"{post_id}_{'see_lz' if see_lz else 'full'}"
        index, _ = self.index_manager.load_index()
        existing = index.get(post_key)

        if not existing:
            return False, ""

        local_floor = existing.get('max_floor_number', '?')
        import_floor = post_entry.get('max_floor_number', '?')
        info = f"{local_floor}楼 → {import_floor}楼"
        return True, info

    def populate_list(self, data: dict):
        self.list_widget.clear()
        self.item_widgets.clear()

        posts = data.get('posts', [])
        if not posts:
            self.folder_label.setText(f"{self.export_dir.name}（空）")
            return

        has_any_valid = False
        for post_entry in posts:
            post_id = post_entry['post_id']
            see_lz = post_entry['see_lz']
            post_key = f"{post_id}_{'see_lz' if see_lz else 'full'}"
            display_name = post_entry.get('display_name', post_key)

            conflict, conflict_info = self._get_local_info(post_entry)
            valid, _ = get_post_integrity(self.export_dir, post_entry)

            if valid:
                has_any_valid = True

            item_widget = ImportItemWidget(
                post_key, display_name,
                local_info=conflict_info,
                conflict=conflict,
                valid=valid,
            )

            item = QListWidgetItem()
            item.setSizeHint(QSize(item_widget.minimumWidth(), item_widget.minimumHeight()))
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, item_widget)
            self.item_widgets[post_key] = item_widget

        self.folder_label.setText(f"{self.export_dir.name}（{len(posts)}个帖子）")
        self.import_btn.setEnabled(has_any_valid)
        self.select_all_btn.setEnabled(has_any_valid)
        self.deselect_all_btn.setEnabled(has_any_valid)

    def reset_state(self):
        self.export_data = None
        self.export_dir = None
        self.item_widgets.clear()
        self.list_widget.clear()
        self.folder_label.setText("未选择文件夹")
        self.open_btn.setEnabled(True)
        self.import_btn.setEnabled(False)
        self.select_all_btn.setEnabled(False)
        self.deselect_all_btn.setEnabled(False)

    def select_all(self):
        for w in self.item_widgets.values():
            w.set_checked(True)

    def deselect_all(self):
        for w in self.item_widgets.values():
            w.set_checked(False)

    def do_import(self):
        checked = [key for key, w in self.item_widgets.items() if w.is_checked()]
        if not checked:
            QMessageBox.information(self, "提示", "请先勾选要导入的帖子。")
            return

        reply = QMessageBox.question(
            self, "确认导入",
            f"确定要导入选中的 {len(checked)} 个帖子吗？\n"
            "已存在的帖子将会询问是否合并。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.No:
            return

        self.set_controls_enabled(False)

        success, skipped, failed = import_selected(
            self.export_dir,
            self.export_data,
            checked,
            self.index_manager,
            parent=self,
        )

        msg = f"导入完成！成功: {success}, 跳过: {skipped}, 失败: {failed}"
        QMessageBox.information(self, "导入完成", msg)

        self.reset_state()

    def set_controls_enabled(self, enabled: bool):
        self.open_btn.setEnabled(enabled)
        self.import_btn.setEnabled(enabled)
        self.select_all_btn.setEnabled(enabled)
        self.deselect_all_btn.setEnabled(enabled)
