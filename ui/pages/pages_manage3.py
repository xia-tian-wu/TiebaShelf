import os
import json
import webbrowser
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QCheckBox, QFrame, QMessageBox, QSizePolicy,
    QAbstractItemView, QMenu, QApplication, QComboBox, QLineEdit
)
from PySide6.QtCore import Qt, Signal, QThread, QSize, Slot
from PySide6.QtGui import QContextMenuEvent, QCursor, QAction, QGuiApplication, QMouseEvent
from spider.index_manage import IndexManager
from spider.utils import json_to_md_path
from ui.pages.functions.async_worker import AsyncWorker
from ui.pages.markdown_viewer_page import MarkdownViewerWindow
from logger import logger
import asyncio
import os

from ui.pages.functions.toggle_switch import ToggleSwitch

class ManageItemWidget(QWidget):
    """单个帖子的管理项（含按钮）"""
    update_requested = Signal(str)      # post_key
    recrawl_requested = Signal(str)
    delete_requested = Signal(str)
    selection_changed = Signal(str, bool)  # 用于批量模式
    open_in_viewer_requested = Signal(str, str)  # file_path, display_name

    def __init__(self, post_key: str, display_name: str, url: str, file_path: str, parent=None):
        super().__init__(parent)
        self.post_key = post_key
        self.display_name = display_name
        self.url = url
        self.file_path = file_path
        self.is_batch_mode = False
        self.checkbox = None
        self.update_btn = None
        self.recrawl_btn = None
        self.delete_btn = None
        self.init_ui()

    def init_ui(self):
        self._hlayout = QHBoxLayout()
        self._hlayout.setContentsMargins(5, 5, 5, 5)

        # 左侧：显示名称
        self.name_label = QLabel(self.display_name)
        self.name_label.setStyleSheet("font-size: 13px;")
        self.name_label.setMinimumWidth(200)  # 设置最小宽度
        self.name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)  # 允许扩展
        self._hlayout.addWidget(self.name_label)
        
        self._hlayout.addSpacing(8)

        self._hlayout.addStretch()

        # 右侧：按钮容器（非批量模式）
        self.button_container = QWidget()
        button_layout = QHBoxLayout(self.button_container)
        button_layout.setSpacing(4)
        button_layout.setContentsMargins(0, 0, 0, 0) # 上下左右间距

        self.update_btn = QPushButton("增量")
        self.recrawl_btn = QPushButton("重爬")
        self.delete_btn = QPushButton("删除")
        
        for btn in [self.update_btn, self.recrawl_btn, self.delete_btn]:
            btn.setFixedSize(50, 28)

        # 按钮点击事件
        self.update_btn.clicked.connect(lambda: self.update_requested.emit(self.post_key))
        self.recrawl_btn.clicked.connect(lambda: self.recrawl_requested.emit(self.post_key))
        self.delete_btn.clicked.connect(lambda: self.delete_requested.emit(self.post_key))

        button_layout.addWidget(self.update_btn)
        button_layout.addWidget(self.recrawl_btn)
        button_layout.addWidget(self.delete_btn)

        self._hlayout.addWidget(self.button_container)

        self.setLayout(self._hlayout)
        self.setFixedHeight(40)
        self.set_batch_mode(False)

    def mousePressEvent(self, event: QMouseEvent):
        """处理鼠标点击事件"""
        if event.button() == Qt.MouseButton.LeftButton:
            # 批量模式下禁用左键打开浏览
            if not self.is_batch_mode:
                self.open_in_viewer_requested.emit(self.file_path, self.display_name)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        # 创建菜单
        menu = QMenu(self)
        menu.setObjectName('postMenu')
        
        # 添加“打开本地文件”
        open_file_action = QAction("在默认阅读器中打开Markdown", self)
        open_file_action.triggered.connect(self.open_markdown)
        menu.addAction(open_file_action)

        # 添加"编辑帖子内容"
        edit_action = QAction("编辑帖子内容", self)
        edit_action.triggered.connect(self.open_json_editor)
        menu.addAction(edit_action)

        # 添加"打开所在文件夹"
        open_folder_action = QAction("浏览本地资源文件夹", self)
        open_folder_action.triggered.connect(self.open_post_folder)
        menu.addAction(open_folder_action)
        
        menu.addSeparator()
        
        # 添加“复制链接”
        copy_action = QAction("复制帖子链接", self)
        copy_action.triggered.connect(self.copy_url)
        menu.addAction(copy_action)

        # 添加“使用浏览器打开”
        open_browser_action = QAction("使用浏览器打开", self)
        open_browser_action.triggered.connect(self.open_url_in_browser)
        menu.addAction(open_browser_action)
        
        # 在鼠标点击位置显示菜单
        menu.exec(event.globalPos())
    
    def copy_url(self):
        """将链接复制到剪贴板"""
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(self.url)
        logger.info(f"已复制链接: {self.url}")
    
    def open_url_in_browser(self):
        """使用默认浏览器打开链接"""
        try:
            if not self.url:
                QMessageBox.warning(self, "警告", "URL为空，无法打开")
                return
            
            # 检查URL格式，如果不是以http或https开头，则添加https://
            url = self.url.strip()
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            # 使用webbrowser打开URL
            webbrowser.open(url)
            logger.info(f"正在使用浏览器打开链接: {url}")
            
        except Exception as e:
            logger.error(f"打开链接失败: {str(e)}")
            QMessageBox.critical(self, "错误", f"无法打开链接:\n{str(e)}")
    
    def get_md_path(self):
        md_file = json_to_md_path(self.file_path)
        folder_path = os.path.dirname(md_file)
        return md_file, folder_path
    
    def open_markdown(self):
        """使用系统默认程序打开 MD 文件"""
        md_file, _ = self.get_md_path()
        if os.path.exists(md_file):
            os.startfile(md_file)  # Windows 专用，会调用默认程序（如 VSCode）
        else:
            QMessageBox.warning(self, "提示", f"找不到本地文件：\n{md_file}")
    
    def open_post_folder(self):
        """打开文件所在的文件夹"""
        _, folder_path = self.get_md_path()
        if os.path.exists(folder_path):
            os.startfile(folder_path)
        else:
            QMessageBox.warning(self, "提示", "文件夹尚未创建或已被删除")

    def open_json_editor(self):
        """打开JSON编辑器"""
        from ui.pages.functions.json_editor import JsonEditorWindow
        from config import POSTS_DIR
        json_path = Path(self.file_path) if Path(self.file_path).is_absolute() else POSTS_DIR / Path(self.file_path).name
        if not json_path.exists():
            QMessageBox.warning(self, "提示", f"找不到帖子JSON文件:\n{json_path}")
            return

        # 如果编辑器已打开，激活它
        editor_ref = getattr(self, '_json_editor', None)
        if editor_ref is not None:
            if editor_ref.isVisible():
                editor_ref.activateWindow()
                editor_ref.raise_()
                return
            self._json_editor = None

        editor = JsonEditorWindow(str(json_path), self.display_name)
        editor.destroyed.connect(lambda: self._clear_json_editor(editor))
        self._json_editor = editor
        editor.show()

    def _clear_json_editor(self, editor):
        if getattr(self, '_json_editor', None) is editor:
            self._json_editor = None

    def set_batch_mode(self, enabled: bool):
        self.is_batch_mode = enabled
        if enabled:
            if not self.checkbox:
                self.checkbox = QCheckBox()
                self.checkbox.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
                self.checkbox.toggled.connect(
                    lambda checked: self.selection_changed.emit(self.post_key, checked)
                )
                self._hlayout.insertWidget(0, self.checkbox)
                self._hlayout.insertSpacing(1, 8)
            self.checkbox.show()
            self.button_container.hide()
        else:
            if self.checkbox:
                self.checkbox.hide()
            self.button_container.show()

    def set_buttons_enabled(self, enabled: bool):
        """禁用/启用单个帖子的按钮"""
        if self.update_btn:
            self.update_btn.setEnabled(enabled)
        if self.recrawl_btn:
            self.recrawl_btn.setEnabled(enabled)
        if self.delete_btn:
            self.delete_btn.setEnabled(enabled)


class PageManage(QWidget):
    def __init__(self, spider_instance=None, main_window=None):
        super().__init__()
        self.main_window = main_window
        self.spider = spider_instance
        self.worker_thread = None      # 统一管理工作线程，避免多线程混乱
        self.worker = None             # 统一管理工作实例
        self.items = {}  # post_key -> ManageItemWidget
        self.selected_keys = set()  # 修复：初始化为set
        self.batch_mode = False
        self.index_manager = IndexManager()
        self.progress_mgr = main_window.global_progress_mgr if main_window else None
        self.is_task_running = False  # 全局任务锁
        self.viewer_window = None  # Markdown 阅读器窗口实例

        self.init_ui()
        # 初始化时加载帖子列表
        self.load_posts()
        
        # 绑定主窗口切换页面信号（实现切到管理页自动刷新）
        if self.main_window and hasattr(self.main_window, 'page_switched'):
            self.main_window.page_switched.connect(self.on_page_switched)

    def init_ui(self):
        layout = QVBoxLayout()

        # 顶部：标题
        top_layout = QHBoxLayout()
        title = QLabel("【管理功能区】")
        title.setStyleSheet("font-weight: bold; font-size: 14px;color: #333333;")
        top_layout.addWidget(title)
        layout.addLayout(top_layout)

        # 功能行：刷新按钮，输入选择框，批量模式开关
        function_layout = QHBoxLayout()

        # 刷新按钮
        self.refresh_btn = QPushButton("刷新列表")
        self.refresh_btn.setFixedSize(80, 30)
        self.refresh_btn.clicked.connect(self.load_posts)
        
        # === 一体化搜索框：下拉框 + 输入框 ===
        self.search_widget = QWidget()
        self.search_widget.setMaximumWidth(2000)  # 最大宽度确保填充
        self.search_widget.setObjectName("searchWidget")
        
        search_layout = QHBoxLayout(self.search_widget)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(0)  # 设置间距为0，让下拉框和输入框连在一起

        # 下拉框
        self.type_filter_combo = QComboBox()
        self.type_filter_combo.setToolTip("点击选择帖子类型过滤")
        self.type_filter_combo.addItems(["  全部", "  只看楼主", "  完整版"])
        self.type_filter_combo.setFixedWidth(80)
        self.type_filter_combo.setFixedHeight(29)
        self.type_filter_combo.setObjectName("typeFilterCombo")
        self.type_filter_combo.currentTextChanged.connect(self.apply_filters)

        # 搜索输入框
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索帖子...")
        self.search_input.setObjectName("searchInput")
        self.search_input.textChanged.connect(self.apply_filters)

        search_layout.addWidget(self.type_filter_combo)
        search_layout.addWidget(self.search_input)

        # 批量模式标签和开关
        self.mode_label = QLabel('批量模式')
        self.mode_label.setStyleSheet("""
            QLabel {
                font-size: 13px;
                color: #333333;
            }
        """)

        # 批量模式开关
        self.batch_toggle_switch = ToggleSwitch()
        self.batch_toggle_switch.toggled.connect(lambda state: self.toggle_batch_mode(state))

        # 创建一个容器来包装标签和开关，减少间距
        mode_container = QWidget()
        mode_container.setFixedSize(100, 30)
        mode_layout = QHBoxLayout(mode_container)
        mode_layout.setContentsMargins(0, 0, 0, 0)  # 清除边距
        mode_layout.addWidget(self.mode_label)
        mode_layout.addWidget(self.batch_toggle_switch)

        function_layout.addWidget(self.refresh_btn)     # 刷新按钮左对齐                
        function_layout.addWidget(self.search_widget)
        function_layout.addWidget(mode_container)       # 批量模式容器右对齐

        layout.addLayout(function_layout)

        # 中部：帖子列表
        self.list_widget = QListWidget()
        self.list_widget.setObjectName('postsList')
        self.list_widget.setSelectionMode(QAbstractItemView.NoSelection)
        layout.addWidget(self.list_widget)

        # 底部：批量操作按钮（初始隐藏）
        self.batch_button_bar = QWidget()
        batch_btn_layout = QHBoxLayout(self.batch_button_bar)
        
        self.batch_update_btn = QPushButton("批量增量更新")
        self.batch_recrawl_btn = QPushButton("批量重新爬取")
        self.batch_delete_btn = QPushButton("批量删除")
        self.batch_cancel_btn = QPushButton("取消选择")

        # 批量操作按钮事件
        self.batch_update_btn.clicked.connect(self.batch_update)
        self.batch_recrawl_btn.clicked.connect(self.batch_recrawl)
        self.batch_delete_btn.clicked.connect(self.batch_delete)
        self.batch_cancel_btn.clicked.connect(self.clear_selection)

        for btn in [self.batch_update_btn, self.batch_recrawl_btn, self.batch_delete_btn, self.batch_cancel_btn]:
            batch_btn_layout.addWidget(btn)

        self.batch_button_bar.hide()
        layout.addWidget(self.batch_button_bar)

        # 状态标签
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("color: gray; font-size: 12px;")
        layout.addWidget(self.status_label)

        self.setLayout(layout)

    def load_posts(self):
        """加载/刷新所有索引中的帖子"""
        try:
            # 清除现有项
            self.list_widget.clear()
            self.items.clear()
            
            # 记录当前批量模式状态，刷新后复用
            current_batch_mode = self.batch_mode
            self.selected_keys.clear()
            
            # 加载索引数据
            index_data = self.index_manager.load_index()
            if not index_data:
                self.status_label.setText("暂无帖子数据")
            else:
                # 遍历索引数据创建UI项
                for post_key, post_info in index_data.items():
                    display_name = post_info.get('display_name', post_info.get('title', '未知帖子'))
                    url = post_info.get('url', '')
                    file_path = post_info.get('file_path', '')
                    
                    item_widget = ManageItemWidget(post_key, display_name, url, file_path)

                    item_widget.update_requested.connect(self.handle_update)
                    item_widget.recrawl_requested.connect(self.handle_recrawl)
                    item_widget.delete_requested.connect(self.handle_delete)
                    item_widget.selection_changed.connect(self.on_item_selected)
                    item_widget.open_in_viewer_requested.connect(self.open_markdown_in_viewer)
                    item_widget.set_batch_mode(current_batch_mode)

                    item = QListWidgetItem()
                    # 拆分setSizeHint调用，避免一次性传参触发异常
                    w = item_widget.minimumWidth()
                    h = item_widget.minimumHeight()
                    item.setSizeHint(QSize(w, h))
                    
                    self.list_widget.addItem(item)
                    self.list_widget.setItemWidget(item, item_widget)
                    self.items[post_key] = item_widget

                self.status_label.setText(f"共加载 {len(self.items)} 个帖子")
                self.apply_filters()
                
            self.batch_button_bar.setVisible(current_batch_mode)
            self.batch_toggle_switch.setChecked(current_batch_mode)
        
        except Exception as e:
            import traceback
            logger.error(f"加载帖子列表失败: {e}\n{traceback.format_exc()}")
            self.status_label.setText(f"加载失败: {str(e)}")
    
    def apply_filters(self):
        """应用搜索和类型过滤"""
        search_text = self.search_input.text().lower()
        filter_type = self.type_filter_combo.currentText()

        # 遍历所有列表项，根据条件显示/隐藏
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            widget = self.list_widget.itemWidget(item)
            
            # 第一次过滤：根据下拉框选择的类型
            type_match = True
            if filter_type.strip() == "只看楼主":
                type_match = "(只看楼主)" in widget.display_name
            elif filter_type.strip() == "完整版":
                type_match = "(完整版)" in widget.display_name
            
            # 第二次过滤：在第一次过滤的基础上，再根据搜索框内容
            text_match = True  # 默认匹配，除非搜索框有内容
            if search_text:  # 如果搜索框不为空
                text_match = search_text in widget.display_name.lower()
            
            # 只有当两次过滤都通过时才显示
            item.setHidden(not (type_match and text_match))

    def clear_search(self):
        """清空搜索框"""
        self.search_input.clear()

    def open_markdown_in_viewer(self, file_path: str, display_name: str):
        """在独立窗口中打开 Markdown 阅读器"""
        from spider.utils import json_to_md_path
        
        md_path = Path(json_to_md_path(file_path))
        if not md_path.exists():
            # 尝试从 data/posts 路径转换
            md_path = Path(file_path.replace(".json", ".md").replace("posts", "markdowns"))
        
        if not md_path.exists():
            QMessageBox.warning(
                self, 
                "文件不存在", 
                f"找不到 Markdown 文件：\n{md_path}\n\n请确保帖子已正确爬取并保存。"
            )
            return
        
        # 检查窗口是否关闭
        if self.viewer_window is not None:
            # 如果窗口已关闭（isVisible() 为False），则清空引用
            if not self.viewer_window.isVisible():
                self.viewer_window = None
        
        # 创建或获取阅读器窗口
        if self.viewer_window is None:
            self.viewer_window = MarkdownViewerWindow()
        
        # 打开文件
        self.viewer_window.open_markdown(md_path, display_name)
            
        
        # 显示并激活窗口
        self.viewer_window.show()
        self.viewer_window.activateWindow()
        self.viewer_window.raise_()

    def on_page_switched(self, page_index: int):
        """主窗口切换页面时触发：切到管理页（索引1）则刷新"""
        if page_index == 1:  # 管理页是第二个（索引1）
            self.load_posts()

    @Slot(bool)
    def toggle_batch_mode(self, enabled: bool):
        """切换批量模式"""
        self.batch_mode = enabled
        self.batch_button_bar.setVisible(enabled)
        # 根据批量模式状态显示/隐藏刷新按钮
        self.refresh_btn.setVisible(not enabled)
        
        # 更新所有widget的批量模式状态
        for widget in self.items.values():
            widget.set_batch_mode(enabled)
        
        # 如果退出批量模式，清空选中状态
        if not enabled:
            self.clear_selection()  # 只在退出批量模式时清空选择
        else:
            # 进入批量模式时不要清空选择
            self.update_batch_button_state()
            pass

    def on_item_selected(self, post_key: str, checked: bool):
        """处理单个项目的选中状态变化"""
        if checked:
            self.selected_keys.add(post_key)
        else:
            self.selected_keys.discard(post_key)

        # 更新批量按钮状态
        self.update_batch_button_state()

    def update_batch_button_state(self):
        """更新批量按钮的启用状态"""
        has_selection = len(self.selected_keys) > 0
        self.batch_update_btn.setEnabled(has_selection)
        self.batch_recrawl_btn.setEnabled(has_selection)
        self.batch_delete_btn.setEnabled(has_selection)
        self.batch_cancel_btn.setEnabled(has_selection)

    def clear_selection(self):
        """清空选择，同时更新UI"""
        self.selected_keys.clear()
        
        # 更新所有checkbox的UI状态
        for widget in self.items.values():
            if widget.checkbox and widget.checkbox.isChecked():
                widget.checkbox.setChecked(False)
        
        # 更新批量按钮状态
        self.update_batch_button_state()

    def set_all_item_buttons_enabled(self, enabled: bool):
        """启用或禁用所有帖子的按钮"""
        for widget in self.items.values():
            widget.set_buttons_enabled(enabled)

    def disable_all_controls(self):
        """禁用所有控件（包括按钮、刷新、批量模式切换）"""
        # 禁用所有帖子的按钮
        self.set_all_item_buttons_enabled(False)
        
        # 禁用所有帖子的勾选框
        for widget in self.items.values():
            if widget.checkbox:
                widget.checkbox.setEnabled(False)
            
        # 禁用批量操作按钮
        self.batch_update_btn.setEnabled(False)
        self.batch_recrawl_btn.setEnabled(False)
        self.batch_delete_btn.setEnabled(False)
        self.batch_cancel_btn.setEnabled(False)
        
        # 禁用刷新按钮
        self.refresh_btn.setEnabled(False)
        
        # 禁用批量模式切换
        self.batch_toggle_switch.setEnabled(False)

    def enable_all_controls(self):
        """启用所有控件"""
        # 启用所有帖子的按钮
        self.set_all_item_buttons_enabled(True)
        for widget in self.items.values():
            if widget.checkbox:
                widget.checkbox.setEnabled(False)
        
        # 启用批量操作按钮
        self.update_batch_button_state()
        
        # 启用刷新按钮
        self.refresh_btn.setEnabled(True)
        
        # 启用批量模式切换
        self.batch_toggle_switch.setEnabled(True)

    def cleanup_worker(self):
        """清理旧的工作线程和任务实例"""
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.quit()
            self.worker_thread.wait(5000)
        if self.worker:
            self.worker.deleteLater()  # 使用Qt的延迟删除
        self.worker_thread = None
        self.worker = None  
        self.is_task_running = False


    # ========== 单个操作 ==========
    def handle_update(self, post_key: str):
        """处理单个帖子的增量更新"""
        if self.is_task_running:
            QMessageBox.warning(self, "操作受限", "当前有任务正在执行，请等待完成后再操作。")
            return
            
        # 获取帖子信息
        try:
            index_data = self.index_manager.load_index()
            if post_key not in index_data:
                QMessageBox.warning(self, "错误", f"帖子 {post_key} 在索引中不存在。")
                return
                
            post_info = index_data[post_key]
            url = post_info['url']
            
            # 启动异步任务
            self.start_async_task(update_urls=[url], post_keys=[post_key], task_type="update")
        except Exception as e:
            logger.error(f"获取帖子信息失败: {e}")
            QMessageBox.critical(self, "错误", f"获取帖子信息失败: {str(e)}")

    def handle_recrawl(self, post_key: str):
        """处理单个帖子的重新爬取"""
        if self.is_task_running:
            QMessageBox.warning(self, "操作受限", "当前有任务正在执行，请等待完成后再操作。")
            return
            
        # 获取帖子信息
        try:
            index_data = self.index_manager.load_index()
            if post_key not in index_data:
                QMessageBox.warning(self, "错误", f"帖子 {post_key} 在索引中不存在。")
                return
                
            post_info = index_data[post_key]
            url = post_info['url']
            
            # 启动异步任务（重新爬取 = 新爬取）
            self.start_async_task(recrawl_urls=[url], post_keys=[post_key], task_type="recrawl")
        except Exception as e:
            logger.error(f"获取帖子信息失败: {e}")
            QMessageBox.critical(self, "错误", f"获取帖子信息失败: {str(e)}")

    def handle_delete(self, post_key: str):
        """处理单个帖子的删除"""
        if self.is_task_running:
            QMessageBox.warning(self, "操作受限", "当前有任务正在执行，请等待完成后再操作。")
            return
            
        # 获取帖子信息
        try:
            index_data = self.index_manager.load_index()
            if post_key not in index_data:
                QMessageBox.warning(self, "错误", f"帖子 {post_key} 在索引中不存在。")
                return
                
            post_info = index_data[post_key]
            post_id = post_info['post_id']
            see_lz = post_info['see_lz']
            
            # 确认删除
            reply = QMessageBox.question(
                self, 
                "确认删除", 
                f"确定要删除帖子 '{post_info['display_name']}' 吗？\n此操作将删除所有相关数据。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                # 禁用相关控件
                self.disable_all_controls()
                self.is_task_running = True
                
                # 执行删除
                success = self.index_manager.delete_post(post_id, see_lz)
                
                if success:
                    # 删除成功，重新加载列表
                    self.load_posts()
                    self.status_label.setText(f"删除帖子 {post_info['display_name']} 成功")
                else:
                    self.status_label.setText(f"删除帖子 {post_info['display_name']} 失败")
                    
                # 恢复控件状态
                self.enable_all_controls()
                self.is_task_running = False
        except Exception as e:
            logger.error(f"删除帖子失败: {e}")
            self.status_label.setText(f"删除失败: {str(e)}")
            self.enable_all_controls()
            self.is_task_running = False

    # ========== 批量操作 ==========
    def batch_update(self):
        """批量增量更新"""
        if self.is_task_running:
            QMessageBox.warning(self, "操作受限", "当前有任务正在执行，请等待完成后再操作。")
            return
            
        if not self.selected_keys:
            QMessageBox.information(self, "提示", "请先选择要操作的帖子。")
            return
        
        try:
            # 获取选中帖子的URL列表
            index_data = self.index_manager.load_index()
            update_urls = []
            
            for post_key in self.selected_keys:
                if post_key in index_data:
                    update_urls.append(index_data[post_key]['url'])
            
            if not update_urls:
                QMessageBox.information(self, "提示", "没有有效的帖子需要更新。")
                return
                
            # 启动异步任务
            self.start_async_task(update_urls=update_urls, post_keys=list(self.selected_keys), task_type="update")
        except Exception as e:
            logger.error(f"批量更新准备失败: {e}")
            QMessageBox.critical(self, "错误", f"批量更新准备失败: {str(e)}")

    def batch_recrawl(self):
        """批量重新爬取"""
        if self.is_task_running:
            QMessageBox.warning(self, "操作受限", "当前有任务正在执行，请等待完成后再操作。")
            return
            
        if not self.selected_keys:
            QMessageBox.information(self, "提示", "请先选择要操作的帖子。")
            return
        
        try:
            # 获取选中帖子的URL列表
            index_data = self.index_manager.load_index()
            new_urls = []
            
            for post_key in self.selected_keys:
                if post_key in index_data:
                    new_urls.append(index_data[post_key]['url'])
            
            if not new_urls:
                QMessageBox.information(self, "提示", "没有有效的帖子需要重新爬取。")
                return
                
            # 启动异步任务（重新爬取 = 新爬取）
            self.start_async_task(recrawl_urls=new_urls, post_keys=list(self.selected_keys), task_type="recrawl")
        except Exception as e:
            logger.error(f"批量重新爬取准备失败: {e}")
            QMessageBox.critical(self, "错误", f"批量重新爬取准备失败: {str(e)}")

    def batch_delete(self):
        """批量删除"""
        if self.is_task_running:
            QMessageBox.warning(self, "操作受限", "当前有任务正在执行，请等待完成后再操作。")
            return
            
        if not self.selected_keys:
            QMessageBox.information(self, "提示", "请先选择要操作的帖子。")
            return
        
        # 确认删除
        reply = QMessageBox.question(
            self, 
            "确认批量删除", 
            f"确定要删除选中的 {len(self.selected_keys)} 个帖子吗？\n此操作将删除所有相关数据。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                # 禁用相关控件
                self.disable_all_controls()
                self.is_task_running = True
                
                # 执行删除
                index_data = self.index_manager.load_index()
                success_count = 0
                failed_count = 0
                
                for post_key in self.selected_keys:
                    if post_key in index_data:
                        post_info = index_data[post_key]
                        post_id = post_info['post_id']
                        see_lz = post_info['see_lz']
                        
                        success = self.index_manager.delete_post(post_id, see_lz)
                        if success:
                            success_count += 1
                        else:
                            failed_count += 1
                
                # 删除完成后重新加载列表
                self.load_posts()
                self.status_label.setText(f"批量删除完成：成功 {success_count} 个，失败 {failed_count} 个")
                
                # 清空选中状态
                self.clear_selection()
                
                # 恢复控件状态
                self.enable_all_controls()
                self.is_task_running = False
            except Exception as e:
                logger.error(f"批量删除失败: {e}")
                self.status_label.setText(f"批量删除失败: {str(e)}")
                self.enable_all_controls()
                self.is_task_running = False

    def start_async_task(self, new_urls=None, update_urls=None, recrawl_urls=None, post_keys=None, task_type="update"):
        """启动异步任务"""

        # 关键：设置新的事件循环，确保线程安全
        asyncio.set_event_loop(asyncio.new_event_loop())
        self.cleanup_worker()

        new_urls = new_urls or []
        update_urls = update_urls or []
        recrawl_urls = recrawl_urls or []
        total = len(new_urls) + len(update_urls) + len(recrawl_urls)

        if total == 0:
            return

        # ===== 启动进度管理 =====
        self.is_task_running = True
        self.progress_mgr.start_task(total_items=total, current_page=self)  # 只需总数！

        # ===== 创建线程 =====
        self.worker_thread = QThread()
        self.worker = AsyncWorker(new_urls, update_urls, recrawl_urls)
        self.worker.moveToThread(self.worker_thread)

        # ===== 连接信号 =====
        self.worker_thread.started.connect(self.worker.run_async_task)
        self.worker.finished.connect(self.on_task_finished)
        self.worker.error.connect(self.on_task_error)
        
        # 关键：连接新信号！
        self.worker.task_completed.connect(self._on_task_completed)
        
        # 启动任务并更新状态
        self.worker_thread.start()
        total = len(new_urls or []) + len(update_urls or []) + len(recrawl_urls or [])

        # 字典映射：task_type → (任务名, 对应数值)
        task_map = {
            "update": ("增量更新", len(update_urls or [])),
            "recrawl": ("重新爬取", len(recrawl_urls or []))

        }
        # 取对应值（默认值防止未知task_type报错）
        task_name, show_count = task_map.get(task_type, ("未知任务", 0))
        self.status_label.setText(f"处理中（总{total}个）：{task_name}{show_count}个")
            

    def on_task_finished(self, results):
        """单一异步任务完成回调"""
        self.cleanup_worker()
        self.enable_all_controls()

        # 统计结果
        success_count = sum(1 for r in results if r['status'] in ['success', 'updated'])
        error_count = sum(1 for r in results if r['status'] == 'error')
        skip_count = len(results) - success_count - error_count

        # 更新UI+提示
        self.status_label.setText(f"完成！成功: {success_count}, 失败: {error_count}, 跳过: {skip_count}")
        
        QMessageBox.information(
            self, "完成",
            f"处理完成！\n成功: {success_count}\n失败: {error_count}\n跳过: {skip_count}"
        )
        self.cleanup_after_task()
        self.load_posts()

    def on_task_error(self, error_msg):
        """异步任务错误回调"""
        self.cleanup_worker()
        self.enable_all_controls()
        
        self.status_label.setText("发生错误")
        QMessageBox.critical(self, "错误", f"任务过程中发生错误：\n{error_msg}")
        self.cleanup_after_task()

    def _on_task_completed(self, url: str, task_type: str):
        """每个URL任务完成时调用"""
        # 让 ProgressManager 累计计数，并记住最近的任务类型
        self.progress_mgr.update_item(task_type)

    def on_task_finish(self, original_states):
        """任务结束时：根据原始状态恢复控件"""
        self.enable_all_controls()

    def cleanup_after_task(self):
        """任务完成后的清理工作"""
        self.is_task_running = False
        if self.progress_mgr:
            self.progress_mgr.finish_all() 
        self.cleanup_worker()
        
        if self.batch_mode:  # 只在当前是批量模式时才退出
            self.toggle_batch_mode(False)

    def on_task_start(self):
        """任务开始时：记录控件原始状态，并禁用关键按钮"""
        # 1. 记录当前控件状态（如按钮是否可用）
        original_states = {
            "start_button": self.enable_all_controls,
            "test_button": self.enable_all_controls,
            "see_lz_checkbox": self.enable_all_controls,
            "url_input": self.enable_all_controls  # 这里是为了兼容性
        }
        # 2. 禁用任务期间不允许操作的控件
        self.disable_all_controls()

        # 3. 返回原始状态，让进度管理器保存
        return original_states