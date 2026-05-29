from PySide6.QtWidgets import QMainWindow, QVBoxLayout, QHBoxLayout, QPushButton, QTabWidget, QMessageBox, QWidget
from PySide6.QtCore import Slot, Qt
from PySide6.QtGui import QIcon
from pathlib import Path
from ui.pages.functions.markdown_viewer import MarkdownViewer
from config import SOURCE_PATH

class MarkdownViewerWindow(QMainWindow):
    """Markdown 阅读器窗口 - 独立窗口，支持多标签页管理"""

    def __init__(self, parent=None):
        super().__init__(None)
        self.setWindowTitle("帖子阅读器")
        self.resize(1200, 800)
        self.viewers = {}  # tab_id -> MarkdownViewer
        
        icon_path = SOURCE_PATH / 'ui' / 'momo.ico'
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
            
        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        central_widget.setLayout(layout)

        # 标签页容器
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)  # 启用标签页关闭按钮
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        self.tab_widget.setDocumentMode(True)  # 更简洁的标签页样式
        self.tab_widget.setStyleSheet("""
    QTabBar {
    background-color: #f5f5f5;
    }
    QTabWidget::pane {
        border: 1px solid #d0d0d0;
        background-color: white;
    }
    QTabBar::tab {
        background-color: #e0e0e0;
        color: #555555;
        padding: 8px 16px;
        margin-right: 2px;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
        min-width: 120px;
    }
    QTabBar::tab:selected {
        background-color: #d0d0d0;
        color: #333333;
        font-weight: bold;
    }
    QTabBar::tab:hover:!selected {
        background-color: #d0d0d0;
    }

""")

        layout.addWidget(self.tab_widget)

    @Slot(int)
    def close_tab(self, index: int):
        """关闭指定索引的标签页"""
        if index < 0:
            return

        # 获取要关闭的 widget
        widget = self.tab_widget.widget(index)

        if widget:
            # 从字典中移除
            for tab_id, viewer in list(self.viewers.items()):
                if viewer == widget:
                    del self.viewers[tab_id]
                    break

            # 关闭并删除 widget
            widget.deleteLater()
            self.tab_widget.removeTab(index)

    def open_markdown(self, md_path: Path, display_name: str = "") -> bool:
        """在标签页中打开 Markdown 文件"""
        try:
            # 检查是否已经打开
            for tab_id, viewer in self.viewers.items():
                if viewer.current_md_path == md_path:
                    # 已经打开，切换到该标签
                    for i in range(self.tab_widget.count()):
                        if self.tab_widget.widget(i) == viewer:
                            self.tab_widget.setCurrentIndex(i)
                            return True

            # 创建新的阅读器实例
            viewer = MarkdownViewer()

            # 加载 Markdown 文件
            if not viewer.load_markdown(md_path):
                viewer.deleteLater()
                return False

            # 设置标签页标题
            tab_title = display_name if display_name else md_path.stem
            if len(tab_title) > 20:
                tab_title = tab_title[:17] + "..."

            # 添加到标签页
            tab_index = self.tab_widget.addTab(viewer, tab_title)
            self.tab_widget.setCurrentIndex(tab_index)

            # 保存到字典
            tab_id = f"tab_{md_path.stem}_{tab_index}"
            self.viewers[tab_id] = viewer

            return True

        except Exception as e:
            QMessageBox.critical(
                self,
                "打开失败",
                f"无法打开 Markdown 文件：\n{str(e)}"
            )
            return False

    def clear_all(self):
        """关闭所有标签页"""
        while self.tab_widget.count() > 0:
            self.close_tab(0)
        self.viewers.clear()
        
    def closeEvent(self, event):
        """窗口关闭时清空所有标签页和缓存"""
        self.clear_all()  # 调用已有方法清空标签页
        self.viewers.clear()  # 确保字典清空
        event.accept()