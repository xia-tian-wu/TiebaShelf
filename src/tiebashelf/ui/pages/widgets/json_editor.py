"""帖子 JSON 编辑器 — 提供楼层内容/图片的可视化修改界面。

用户修改以补丁文件形式保存到 PATCHES_DIR，
原始 JSON 不被修改，Markdown 生成时自动合并补丁。
"""
import json
import shutil
import time
import re
from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QLineEdit, QTextEdit, QFileDialog, QMessageBox,
    QSplitter, QFrame, QScrollArea, QFormLayout, QGroupBox, QToolButton, QToolBar, QSizePolicy,
    QAbstractItemView
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon

from tiebashelf.config import MARKDOWN_DIR, IMAGES_DIR, PATCHES_DIR, PACKAGE_DIR
from tiebashelf.logger import logger
from tiebashelf.markdown_builder import _render_markdown_from_post_data
from tiebashelf.spider.utils import post_subdir_name


class JsonEditorWindow(QMainWindow):
    """帖子编辑主窗口。左侧楼层列表，右侧编辑面板 + 修改提示。"""

    def __init__(self, json_path: str, display_name: str, parent=None):
        super().__init__(None)
        self.json_path = Path(json_path)
        self.display_name = display_name
        self.post_data = None
        self.patch_data = None
        self.original_floors = {}
        self.floor_widgets = {}
        self.floor_modifications = {}
        self.image_dir = Path()
        self._hint_expanded = False

        icon_path = PACKAGE_DIR / 'ui' / 'momo.ico'
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.init_data()
        self.init_ui()

    def init_data(self):
        """加载原始 JSON、补丁文件，合并数据并初始化修改状态。"""
        with open(self.json_path, 'r', encoding='utf-8') as f:
            self.post_data = json.load(f)

        post_id = self.post_data['post_id']
        see_lz = self.post_data.get('see_lz', False)
        subdir = post_subdir_name(post_id, see_lz)
        self.patch_image_dir = PATCHES_DIR / subdir
        self.patch_image_dir.mkdir(parents=True, exist_ok=True)

        stored_dir = self.post_data.get('images_dir', '')
        if not stored_dir or not Path(stored_dir).exists():
            self.image_dir = IMAGES_DIR / subdir
            self.image_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.image_dir = Path(stored_dir)

        self.patch_path = PATCHES_DIR / subdir / "patch.json"
        self.patch_data = self._load_patch()

        for floor in self.post_data['floors']:
            fn = floor['floor_number']
            self.original_floors[fn] = dict(floor)

        if self.patch_data and 'edits' in self.patch_data:
            for fn_str, edited_floor in self.patch_data['edits'].items():
                fn = int(fn_str)
                for i, floor in enumerate(self.post_data['floors']):
                    if floor['floor_number'] == fn:
                        floor.update(edited_floor)
                        break

        for floor in self.post_data['floors']:
            fn = floor['floor_number']
            self.floor_modifications[fn] = dict(floor)

    def _load_patch(self):
        """读取补丁文件，失败返回 None。"""
        if self.patch_path.exists():
            try:
                with open(self.patch_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载补丁文件失败: {e}")
        return None

    def init_ui(self):
        """构建窗口布局：左右分割面板 + 顶部工具栏。"""
        self.setWindowTitle(f"编辑帖子内容 ➤ {self.display_name}")
        self.setMinimumSize(900, 650)
        self.resize(1050, 720)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        left_panel = self._build_left_panel()
        right_panel = self._build_right_panel()

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([220, 830])

        main_layout.addWidget(splitter)

        self._create_toolbar()
        self._apply_styles()
        self._update_hints()

    def _create_toolbar(self):
        """创建顶部工具栏：左侧"撤销修改"，右侧"保存修改"。"""
        toolbar = self.addToolBar("编辑工具栏")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setFixedHeight(36)
        toolbar.setStyleSheet(
            "QToolBar { background: #f5f6f8; border-bottom: 1px solid #d0d5dd; padding: 4px 8px; }"
            "QToolButton { background: #4897e7; color: white; border: none; border-radius: 4px; padding: 4px 14px; min-height: 24px; font-size: 13px; }"
            "QToolButton:hover { background: #3689db; }"
            "QToolButton:pressed { background: #2169b1; }"
        )

        undo_btn = QToolButton()
        undo_btn.setText("撤销修改")
        undo_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        undo_btn.clicked.connect(self._undo_and_close)
        toolbar.addWidget(undo_btn)

        spacer_left = QWidget()
        spacer_left.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        toolbar.addWidget(spacer_left)

        hint_label = QLabel("请勿手动修改 [图片：] / [补丁：] 标记，应通过图片列表管理")
        hint_label.setStyleSheet("color: #999; font-size: 12px;")
        toolbar.addWidget(hint_label)

        spacer_right = QWidget()
        spacer_right.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        toolbar.addWidget(spacer_right)

        save_btn = QToolButton()
        save_btn.setText("保存修改")
        save_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        save_btn.clicked.connect(self._save_and_close)
        toolbar.addWidget(save_btn)

    def _build_left_panel(self):
        """构建左侧楼层列表面板。"""
        panel = QWidget()
        panel.setObjectName("editorLeftPanel")
        panel.setMinimumWidth(180)
        panel.setMaximumWidth(280)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 6, 6, 6)

        title_row = QWidget()
        title_layout = QHBoxLayout(title_row)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(4)

        title = QLabel("楼层列表")
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #333;")
        title_layout.addWidget(title)

        self.floor_jump_input = QLineEdit()
        self.floor_jump_input.setPlaceholderText("输入跳转楼层数")
        self.floor_jump_input.setFixedWidth(120)
        self.floor_jump_input.setStyleSheet(
            "border: 1px solid #ccc; border-radius: 3px; padding: 2px 6px; font-size: 12px;"
            "background: white; color: #333;"
        )
        self.floor_jump_input.returnPressed.connect(self._jump_to_floor_from_input)
        title_layout.addWidget(self.floor_jump_input)

        layout.addWidget(title_row)

        self.floor_list = QListWidget()
        self.floor_list.setObjectName("editorFloorList")
        self.floor_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.floor_list.currentRowChanged.connect(self._on_floor_selected)

        for floor in self.post_data['floors']:
            fn = floor['floor_number']
            author = floor.get('author', '未知')
            item = QListWidgetItem(f"[{fn}楼] {author}")
            item.setData(Qt.ItemDataRole.UserRole, fn)
            self.floor_list.addItem(item)

        layout.addWidget(self.floor_list)
        return panel

    def _build_right_panel(self):
        """构建右侧面板：修改提示 + 楼层编辑滚动区。"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.hint_toggle = QToolButton()
        self.hint_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.hint_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hint_toggle.setText("▸ 当前修改：0 个楼层")
        self.hint_toggle.setStyleSheet(
            "QToolButton { background: none; border: none; color: #888; font-size: 12px; text-align: left; padding: 2px 0; }"
            "QToolButton:hover { color: #4897e7; }"
        )
        self.hint_toggle.clicked.connect(self._toggle_hints)
        layout.addWidget(self.hint_toggle)

        self.hint_content = QLabel("暂无修改")
        self.hint_content.setStyleSheet(
            "color: #666; font-size: 12px; padding: 4px 8px; background: #f5f6f8; border-radius: 4px;"
        )
        self.hint_content.setWordWrap(True)
        self.hint_content.hide()
        layout.addWidget(self.hint_content)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #ddd;")
        layout.addWidget(sep)

        self.floor_info_label = QLabel("请从左侧选择一个楼层")
        self.floor_info_label.setStyleSheet("color: #999; font-size: 13px; padding: 8px 0;")
        layout.addWidget(self.floor_info_label)

        self.scroll: QScrollArea = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        layout.addWidget(self.scroll)

        self.current_floor_widget = None
        return panel

    def _on_floor_selected(self, row):
        """切换楼层选中：保存旧楼层修改，加载新楼层编辑器。"""
        if row < 0:
            return
        item = self.floor_list.item(row)
        floor_num = item.data(Qt.ItemDataRole.UserRole)

        if self.current_floor_widget:
            self._save_current_modifications()

        for floor in self.post_data['floors']:
            if floor['floor_number'] == floor_num:
                self.floor_info_label.hide()
                if self.current_floor_widget:
                    self.current_floor_widget.deleteLater()
                floor_data = dict(floor)
                if floor_num in self.floor_modifications:
                    floor_data.update(self.floor_modifications[floor_num])
                self.current_floor_widget = FloorEditWidget(floor_data, self.image_dir, self.patch_image_dir, self)
                self.current_floor_widget.modification_changed.connect(self._on_floor_modified)
                self.scroll.setWidget(self.current_floor_widget)
                self.floor_widgets[floor_num] = self.current_floor_widget
                break

    def _jump_to_floor_from_input(self):
        """从跳转输入框获取数字，定位到对应楼层。"""
        text = self.floor_jump_input.text().strip()
        if not text.isdigit():
            QMessageBox.warning(self, "提示", "请输入正确存在的楼层编号")
            self.floor_jump_input.clear()
            return

        target = int(text)
        for i in range(self.floor_list.count()):
            item = self.floor_list.item(i)
            fn = item.data(Qt.ItemDataRole.UserRole)
            if fn == target:
                self.floor_list.setCurrentItem(item)
                self.floor_jump_input.clear()
                return

        QMessageBox.warning(self, "提示", "请输入正确存在的楼层编号")
        self.floor_jump_input.clear()

    def _save_current_modifications(self):
        """将当前楼层编辑器的数据保存到 floor_modifications。"""
        if not self.current_floor_widget:
            return
        try:
            fn = self.current_floor_widget.floor_data['floor_number']
            self.floor_modifications[fn] = self.current_floor_widget.get_modified_floor()
            self._update_hints()
        except RuntimeError:
            pass

    def _on_floor_modified(self):
        """楼层内容变化时，同步更新 floor_modifications 和提示面板。"""
        if self.current_floor_widget:
            try:
                fn = self.current_floor_widget.floor_data['floor_number']
                self.floor_modifications[fn] = self.current_floor_widget.get_modified_floor()
            except RuntimeError:
                pass
        self._update_hints()

    @staticmethod
    def _get_hints_from_data(current: dict, original: dict, fn: int):
        """对比当前楼层数据与原始数据，返回修改提示列表。"""
        hints = []
        if current.get('content', '') != original.get('content', ''):
            hints.append(f"• {fn}楼 content 已修改")

        orig_img_count = len(original.get('local_images', []))
        curr_img_count = len(current.get('local_images', []))
        if curr_img_count > orig_img_count:
            hints.append(f"• {fn}楼 新增 {curr_img_count - orig_img_count} 张图片")
        elif curr_img_count < orig_img_count:
            hints.append(f"• {fn}楼 删除了 {orig_img_count - curr_img_count} 张图片")

        return hints

    def _update_hints(self):
        """更新修改提示面板和楼层列表标记。"""
        hints = []
        modified_count = 0

        for floor in self.post_data['floors']:
            fn = floor['floor_number']
            original = self.original_floors.get(fn, {})
            mod_data = self.floor_modifications.get(fn)
            if not mod_data:
                continue
            floor_hints = self._get_hints_from_data(mod_data, original, fn)
            if floor_hints:
                modified_count += 1
                hints.extend(floor_hints)

        arrow = "▾" if self._hint_expanded else "▸"

        if modified_count > 0:
            self.hint_toggle.setText(f"{arrow} 当前修改：{modified_count} 个楼层")
            self.hint_content.setText("\n".join(hints))
            if len(hints) <= 2:
                self.hint_content.show()
                self._hint_expanded = True
                self.hint_toggle.setText(f"▾ 当前修改：{modified_count} 个楼层")
            else:
                self.hint_content.hide()
                self._hint_expanded = False
                self.hint_toggle.setText(f"▸ 当前修改：{modified_count} 个楼层")
        else:
            self.hint_toggle.setText("▸ 当前修改：0 个楼层")
            self.hint_content.setText("暂无修改")
            self.hint_content.hide()
            self._hint_expanded = False

        for i in range(self.floor_list.count()):
            item = self.floor_list.item(i)
            fn = item.data(Qt.ItemDataRole.UserRole)
            original = self.original_floors.get(fn, {})
            mod_data = self.floor_modifications.get(fn)
            if mod_data and self._get_hints_from_data(mod_data, original, fn):
                if not item.text().endswith(" ✎"):
                    item.setText(item.text() + " ✎")
            else:
                item.setText(item.text().replace(" ✎", ""))

    def _toggle_hints(self):
        """切换修改提示面板的展开/折叠状态。"""
        self._hint_expanded = not self._hint_expanded
        if self._hint_expanded:
            self.hint_content.show()
            text = self.hint_toggle.text()
            self.hint_toggle.setText(text.replace("▸", "▾"))
        else:
            self.hint_content.hide()
            text = self.hint_toggle.text()
            self.hint_toggle.setText(text.replace("▾", "▸"))

    def _undo_and_close(self):
        """撤销所有修改：删除补丁文件，重生成无补丁的 Markdown，关闭窗口。"""
        if not self.patch_path.exists():
            QMessageBox.information(self, "提示", "未检测到任何已保存的修改")
            return

        reply = QMessageBox.question(
            self, "确认撤销",
            "确定要撤销所有修改吗？\n补丁文件将被删除，帖子恢复为原始内容。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            patch_dir = self.patch_path.parent
            if patch_dir.exists():
                shutil.rmtree(patch_dir)
        except Exception as e:
            QMessageBox.critical(self, "撤销失败", f"删除补丁目录失败:\n{e}")
            return

        with open(self.json_path, 'r', encoding='utf-8') as f:
            self.post_data = json.load(f)
        self.patch_data = None
        self._rebuild_markdown()
        logger.info(f"已撤销修改，补丁文件已删除: {self.patch_path.parent.name}/patch.json")
        self.close()

    def _save_and_close(self):
        """保存补丁文件并关闭窗口。"""
        self._save_current_modifications()

        edits = {}
        for floor in self.post_data['floors']:
            fn = floor['floor_number']
            mod_data = self.floor_modifications.get(fn)
            if mod_data and self._get_hints_from_data(mod_data, self.original_floors.get(fn, {}), fn):
                edits[str(fn)] = mod_data

        if not edits:
            QMessageBox.information(self, "提示", "暂无修改需要保存")
            return

        self.patch_data = {
            "post_id": self.post_data['post_id'],
            "see_lz": self.post_data.get('see_lz', False),
            "modified_at": time.strftime('%Y-%m-%d %H:%M:%S'),
            "edits": edits
        }

        try:
            with open(self.patch_path, 'w', encoding='utf-8') as f:
                json.dump(self.patch_data, f, ensure_ascii=False, indent=2)
            logger.info(f"补丁文件已保存，同步更新: {self.patch_path.parent.name}/patch.json")

            self._rebuild_markdown()

            for fn in edits:
                fn_int = int(fn)
                edited = edits[fn]
                for i, floor in enumerate(self.post_data['floors']):
                    if floor['floor_number'] == fn_int:
                        self.post_data['floors'][i].update(edited)
                        self.original_floors[fn_int] = dict(floor)
                        break
                if fn_int in self.floor_modifications:
                    del self.floor_modifications[fn_int]

            self._update_hints()
            self.close()
        except Exception as e:
            logger.error(f"保存补丁文件失败: {e}")
            QMessageBox.critical(self, "保存失败", f"保存补丁文件失败:\n{str(e)}")

    def _rebuild_markdown(self):
        """合并补丁数据，重新生成 Markdown 文件。"""
        merged = json.loads(json.dumps(self.post_data))
        if self.patch_data and 'edits' in self.patch_data:
            for fn_str, edited_floor in self.patch_data['edits'].items():
                fn = int(fn_str)
                for i, floor in enumerate(merged['floors']):
                    if floor['floor_number'] == fn:
                        merged['floors'][i].update(edited_floor)
                        break

        post_id = merged['post_id']
        see_lz = merged.get('see_lz', False)
        subdir = post_subdir_name(post_id, see_lz)
        image_abs_dir = IMAGES_DIR / subdir
        patch_image_abs_dir = PATCHES_DIR / subdir

        md_content = _render_markdown_from_post_data(merged, image_abs_dir, patch_image_abs_dir=patch_image_abs_dir)

        md_path = MARKDOWN_DIR / f"{self.json_path.stem}.md"
        MARKDOWN_DIR.mkdir(parents=True, exist_ok=True)
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)

    def _apply_styles(self):
        """应用编辑器样式表。"""
        self.setStyleSheet("""
            QWidget#editorLeftPanel {
                background-color: #e9effb;
                border-right: 1px solid #d0d5dd;
            }
            QListWidget#editorFloorList {
                background-color: transparent;
                border: none;
                outline: none;
                font-size: 13px;
                color: #666;
            }
            QListWidget#editorFloorList::item {
                padding: 6px 8px;
                border-radius: 4px;
                margin: 1px 2px;
                color: #666;
            }
            QListWidget#editorFloorList::item:selected {
                background-color: #9bcdf6;
                color: #224953;
            }
            QListWidget#editorFloorList::item:hover:!selected {
                background-color: #d5e3f5;
                color: #444;
            }
            QGroupBox {
                font-size: 13px;
                font-weight: bold;
                color: #888;
                border: 1px solid #ddd;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
                color: #888;
            }
            QToolTip {
                background-color: #fff;
                color: #333;
                border: 1px solid #ccc;
                border-radius: 3px;
                padding: 4px 6px;
                font-size: 12px;
            }
        """)


class FloorEditWidget(QWidget):
    """单个楼层的编辑面板：内容编辑 + 图片管理。"""

    modification_changed = Signal()

    def __init__(self, floor_data: dict, image_dir: Path, patch_image_dir: Path, parent=None):
        super().__init__(parent)
        self.floor_data = floor_data
        self.image_dir = image_dir
        self.patch_image_dir = patch_image_dir
        self.saved_state = dict(floor_data)
        self.images = list(floor_data.get('images', []))
        self.local_images = list(floor_data.get('local_images', []))

        self.init_ui()

    def init_ui(self):
        """构建楼层编辑表单：楼层号、作者（只读）、内容、图片列表。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        fn = self.floor_data['floor_number']
        author = self.floor_data.get('author', '未知')
        post_time = self.floor_data.get('post_time', '')
        ip = self.floor_data.get('ip_location', '')
        device = self.floor_data.get('device', '')
        meta = f"{fn}楼 · {post_time}"
        if ip:
            meta += f" · {ip}"
        if device:
            meta += f" · {device}"

        self.meta_label = QLabel(meta)
        self.meta_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #555; padding-bottom: 4px;")
        layout.addWidget(self.meta_label)

        form_widget = QWidget()
        form_layout = QFormLayout(form_widget)
        form_layout.setSpacing(6)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        author_label = QLabel(author)
        author_label.setStyleSheet("font-size: 13px; color: #666;")
        form_layout.addRow("作者", author_label)

        self.content_edit = QTextEdit()
        self.content_edit.setPlainText(self.floor_data.get('content', ''))
        self.content_edit.setMinimumHeight(120)
        form_layout.addRow("内容", self.content_edit)

        self.image_group = QGroupBox(f"图片 ({len(self.local_images)}张)")
        image_layout = QVBoxLayout(self.image_group)
        image_layout.setSpacing(4)

        self.image_list_widget = QWidget()
        self.image_list_layout = QVBoxLayout(self.image_list_widget)
        self.image_list_layout.setContentsMargins(0, 0, 0, 0)
        self.image_list_layout.setSpacing(2)
        image_layout.addWidget(self.image_list_widget)

        add_btn = QPushButton("+ 添加图片")
        add_btn.setFixedHeight(28)
        add_btn.clicked.connect(self._add_image)
        image_layout.addWidget(add_btn)

        self._refresh_image_list()
        form_layout.addRow("图片", self.image_group)

        layout.addWidget(form_widget)
        layout.addStretch()

        self.content_edit.textChanged.connect(self._on_content_changed)

    def _on_content_changed(self):
        """内容变化时同步图片列表并发出修改信号。"""
        self._sync_content_to_images()
        self.modification_changed.emit()

    def _sync_content_to_images(self):
        """根据 content 中的 [图片：] / [补丁：] 标签同步 local_images 列表。"""
        content = self.content_edit.toPlainText()
        found_crawl = re.findall(r'\[图片：([^\]]+)\]', content)
        found_patch = re.findall(r'\[补丁：([^\]]+)\]', content)

        current_filenames = [Path(p).name for p in self.local_images]

        for fn in found_crawl:
            if fn not in current_filenames:
                full_path = self.image_dir / fn
                if full_path.exists():
                    self.local_images.append(str(full_path))
                    self.images.append(str(full_path))
                    self._refresh_image_list()

        for fn in found_patch:
            if fn not in current_filenames:
                full_path = self.patch_image_dir / fn
                if full_path.exists():
                    self.local_images.append(str(full_path))
                    self.images.append(str(full_path))
                    self._refresh_image_list()

        for i in range(len(self.local_images) - 1, -1, -1):
            fn = Path(self.local_images[i]).name
            if fn not in found_crawl and fn not in found_patch:
                self.local_images.pop(i)
                self.images.pop(i)

        self._update_image_group_title()

    def _refresh_image_list(self):
        """刷新图片列表 UI。"""
        while self.image_list_layout.count():
            item = self.image_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for i, (img_url, local_path) in enumerate(zip(self.images, self.local_images)):
            row = self._build_image_row(i, img_url, local_path)
            self.image_list_layout.addWidget(row)

        self._update_image_group_title()

    def _build_image_row(self, index: int, img_url: str, local_path: str):
        """构建单张图片的显示行（文件名 + 预览 + 删除）。"""
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(4, 2, 4, 2)
        row_layout.setSpacing(6)

        filename = Path(local_path).name
        display_name = filename if len(filename) <= 30 else filename[:27] + "..."

        icon_label = QLabel("📷")
        icon_label.setFixedWidth(20)
        row_layout.addWidget(icon_label)

        name_label = QLabel(display_name)
        name_label.setToolTip(local_path)
        name_label.setStyleSheet("font-size: 12px; color: #333;")
        row_layout.addWidget(name_label, 1)

        preview_btn = QPushButton("预览")
        preview_btn.setFixedSize(50, 26)
        preview_btn.clicked.connect(lambda: self._preview_image(local_path))
        row_layout.addWidget(preview_btn)

        remove_btn = QPushButton("删除")
        remove_btn.setFixedSize(50, 26)
        remove_btn.setStyleSheet("QPushButton { background-color: #e74c3c; color: white; border-radius: 3px; }"
                                  "QPushButton:hover { background-color: #c0392b; }")
        remove_btn.clicked.connect(lambda: self._remove_image(index))
        row_layout.addWidget(remove_btn)

        return row

    def _update_image_group_title(self):
        """更新图片分组框标题。"""
        count = len(self.local_images)
        self.image_group.setTitle(f"图片 ({count}张)")

    def _add_image(self):
        """选择图片文件 → 复制到补丁目录 → 追加 [补丁：] 到 content 末尾。"""
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择图片", "", "图片文件 (*.jpg *.jpeg *.png *.gif *.bmp *.webp)"
        )
        if not files:
            return

        for file_path in files:
            src = Path(file_path)
            filename = src.name
            dest_path = self.patch_image_dir / filename

            if dest_path.exists():
                base = src.stem
                ext = src.suffix
                counter = 1
                while dest_path.exists():
                    dest_path = self.patch_image_dir / f"{base}_{counter}{ext}"
                    counter += 1

            try:
                shutil.copy2(src, dest_path)
            except Exception as e:
                logger.error(f"复制图片失败: {e}")
                QMessageBox.warning(self, "错误", f"复制图片失败:\n{str(e)}")
                continue

            new_filename = dest_path.name
            self.local_images.append(str(dest_path))
            self.images.append(str(src))

            self.content_edit.blockSignals(True)
            current_content = self.content_edit.toPlainText()
            if current_content and not current_content.endswith('\n'):
                self.content_edit.append("")
            self.content_edit.append(f"[补丁：{new_filename}]")
            self.content_edit.blockSignals(False)

        self._refresh_image_list()
        self.modification_changed.emit()

    def _remove_image(self, index: int):
        """删除指定图片：从 content 移除标签，从列表移除路径。"""
        if index < 0 or index >= len(self.local_images):
            return

        filename = Path(self.local_images[index]).name
        tag = f"[图片：{filename}]"

        self.content_edit.blockSignals(True)
        content = self.content_edit.toPlainText()
        if tag not in content:
            tag = f"[补丁：{filename}]"
        if tag in content:
            content = content.replace(tag, "", 1)
            self.content_edit.setPlainText(content)
        self.content_edit.blockSignals(False)

        self.local_images.pop(index)
        self.images.pop(index)

        self._refresh_image_list()
        self.modification_changed.emit()

    def _preview_image(self, stored_path):
        """用系统默认程序打开图片。优先使用存储路径，失败则尝试在图片目录或补丁目录查找。"""
        p = Path(stored_path)
        if p.exists():
            self._open_file(p)
            return

        # 回退：按文件名查找
        filename = p.name
        fallback_path = self.image_dir / filename
        if fallback_path.exists():
            self._open_file(fallback_path)
        else:
            fallback_path = self.patch_image_dir / filename
            if fallback_path.exists():
                self._open_file(fallback_path)
            else:
                QMessageBox.warning(self, "提示", f"图片文件不存在:\n{stored_path}\n\n也未在 {self.image_dir.name} 或 {self.patch_image_dir.name} 中找到 {filename}")

    def _open_file(self, path):
        """调用系统默认程序打开文件。"""
        import subprocess
        subprocess.Popen(['start', '', str(path)], shell=True)

    def is_modified(self):
        """检查楼层是否有修改（仅 content 和 images）。"""
        current = self.get_modified_floor()
        if current.get('content', '') != self.saved_state.get('content', ''):
            return True
        if current.get('images', []) != self.saved_state.get('images', []):
            return True
        if current.get('local_images', []) != self.saved_state.get('local_images', []):
            return True
        return False

    def get_modified_floor(self):
        """获取当前楼层的完整编辑数据。"""
        return {
            'author': self.floor_data.get('author', ''),
            'content': self.content_edit.toPlainText(),
            'images': list(self.images),
            'local_images': list(self.local_images),
            'post_time': self.floor_data.get('post_time', ''),
            'ip_location': self.floor_data.get('ip_location', ''),
            'device': self.floor_data.get('device', ''),
        }

    def get_modification_hints(self, original: dict):
        """生成该楼层的修改提示（供提示面板使用）。"""
        hints = []
        current = self.get_modified_floor()

        if current.get('content', '') != original.get('content', ''):
            hints.append(f"• {self.floor_data['floor_number']}楼 content 已修改")

        orig_img_count = len(original.get('local_images', []))
        curr_img_count = len(current.get('local_images', []))
        if curr_img_count > orig_img_count:
            hints.append(f"• {self.floor_data['floor_number']}楼 新增 {curr_img_count - orig_img_count} 张图片")
        elif curr_img_count < orig_img_count:
            hints.append(f"• {self.floor_data['floor_number']}楼 删除了 {orig_img_count - curr_img_count} 张图片")

        for field, label in [('author', '作者'), ('post_time', '发帖时间'),
                             ('ip_location', 'IP属地'), ('device', '设备')]:
            if current.get(field, '') != original.get(field, ''):
                hints.append(f"• {self.floor_data['floor_number']}楼 {label} 已修改")

        return hints

    def mark_as_saved(self):
        """标记当前状态为已保存（更新 saved_state）。"""
        self.saved_state = self.get_modified_floor()
