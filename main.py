import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QStackedWidget, QTextEdit, QLabel, QFrame, QStatusBar,
    QPushButton, QSizePolicy, QProgressBar, QSizePolicy, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QSharedMemory
from PySide6.QtGui import QPalette, QColor, QIcon
from spider.re_spider import TiebaShelf

from ui.pages.functions.markdown_viewer import cleanup_stale_temp_html
from ui.pages.pages_crawl import PageCrawl
from ui.pages.functions.progress_manager import TaskProgressManager
from ui.pages.pages_manage3 import PageManage
from ui.pages.pages_import import PageImport
from ui.pages.introduction_page import PageFuture
from config import SOURCE_PATH
from logger import setup_logger, add_ui_handler, remove_ui_handler, logger as global_logger

class MainWindow(QMainWindow):
    page_switched = Signal(int)

    def __init__(self, app_instance: QApplication):
        super().__init__()
        cleanup_stale_temp_html()
        self.setWindowTitle("TiebaShelf v2.6")

        self.setMinimumSize(1000, 600)
        icon_path = SOURCE_PATH / 'ui' /'momo.ico'
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        else:
            global_logger.warning(f"图标文件不存在：{icon_path}，使用默认图标")

        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#E9ECEF"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#343A40"))
        app_instance.setPalette(palette)

        # --- 左侧：书签式导航 ---
        self.nav_list = QListWidget()
        self.nav_list.setObjectName("navigationList")
        self.nav_list.addItems(["爬取", "管理", "导入", "项目介绍"])
        self.nav_list.setFixedWidth(100)
        self.nav_list.currentRowChanged.connect(self.switch_page)

        # --- 中间：功能页面堆栈 ---
        self.stacked_widget = QStackedWidget()
        self.global_status_label = QLabel("就绪")
        self.global_status_label.setStyleSheet("color: gray; font-size: 12px;")
        self.global_status_label.hide()

        self.global_progress_bar = QProgressBar()
        self.global_progress_bar.setRange(0, 100)
        self.global_progress_bar.setTextVisible(True)
        self.global_progress_bar.hide()
        self.global_progress_bar.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed
        )

        self.global_progress_mgr = TaskProgressManager(
            status_label=self.global_status_label,
            progress_bar=self.global_progress_bar
        )

        self.spider = TiebaShelf()

        self.middle_container = QWidget()
        self.middle_layout = QVBoxLayout(self.middle_container)

        self.stacked_widget.addWidget(PageCrawl(main_window=self))
        self.stacked_widget.addWidget(PageManage(main_window=self))
        self.stacked_widget.addWidget(PageImport(main_window=self))
        self.stacked_widget.addWidget(PageFuture())
        self.middle_layout.addWidget(self.stacked_widget)

        self.middle_layout.addWidget(self.global_status_label)
        self.middle_layout.addWidget(self.global_progress_bar)

        # --- 右侧：日志区域 ---
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setFixedWidth(160)
        self.log_area.append(" ==== 操作日志 ====")
        self.log_area.append("UI 加载完成，等待任务执行...")
        self.ui_log_handler = add_ui_handler(self.log_area)

        log_container = QWidget()
        log_container.setFixedWidth(160)
        log_layout = QVBoxLayout(log_container)
        log_layout.addWidget(self.log_area)

        clear_log_btn = QPushButton("清空日志")
        clear_log_btn.setObjectName("clearLogButton")
        clear_log_btn.setFixedHeight(30)
        clear_log_btn.setFixedWidth(155)
        clear_log_btn.clicked.connect(self.clear_log)
        log_layout.addWidget(clear_log_btn, alignment=Qt.AlignmentFlag.AlignRight)

        # --- 整体水平布局 ---
        main_layout = QHBoxLayout()
        main_layout.addWidget(self.nav_list)
        main_layout.addWidget(self.middle_container)
        main_layout.addWidget(log_container)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        self.setStatusBar(QStatusBar())
        self.nav_list.setCurrentRow(0)

        global_logger.info("主窗口初始化完成")

    def switch_page(self, index):
        self.stacked_widget.setCurrentIndex(index)
        self.page_switched.emit(index)

    def closeEvent(self, event):
        remove_ui_handler(self.ui_log_handler)
        
        # 关闭Markdown阅读器窗口
        manage_page = self.stacked_widget.widget(1)
        if hasattr(manage_page, 'viewer_window') and manage_page.viewer_window:
            manage_page.viewer_window.close()

        # 关闭所有打开的JSON编辑器
        if hasattr(manage_page, 'items'):
            for item in manage_page.items.values():
                editor = getattr(item, '_json_editor', None)
                if editor is not None:
                    editor.close()

        cleanup_stale_temp_html()
        super().closeEvent(event)

    def clear_log(self):
        self.log_area.clear()
        self.log_area.append(" ==== 操作日志 ====")
        self.log_area.append("日志已清空，等待新任务执行...")
        global_logger.info("日志面板已清空")

    def log(self, msg: str):
        self.log_area.append(msg)


# ======================
# 启动应用
# ======================

if __name__ == "__main__":

    # 创建共享内存段（名称必须唯一）
    shared_mem = QSharedMemory("TiebaShelf_SingleInstance")

    # 尝试创建共享内存
    if not shared_mem.create(1):  # 1 字节足够
        # 创建失败 → 已有实例在运行
        QMessageBox.critical(
            None,
            "程序已在运行",
            "“贴吧书库”已经在运行中。\n\n请切换到已打开的窗口。"
        )
        sys.exit(1)  # 退出新启动的实例

    # 继续正常启动...
    app = QApplication(sys.argv)
    window = MainWindow(app)
    window.resize(1000, 600)
    window.show()

    # ===== 加载样式表 =====
    style_path = SOURCE_PATH / "ui" / "style.css"

    try:
        with open(style_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())
    except FileNotFoundError:
        global_logger.warning(f"样式文件不存在：{style_path}，使用默认样式")

    # 正常退出时会自动释放 shared_mem（RAII）
    sys.exit(app.exec())
