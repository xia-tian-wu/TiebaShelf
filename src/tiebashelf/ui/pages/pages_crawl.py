import re
import asyncio
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTextEdit, QHBoxLayout, QPushButton,
    QLabel, QMessageBox, QFrame, QDialog
)
from PySide6.QtCore import QThread, QTimer
from tiebashelf.ui.pages.widgets.toggle_switch import ToggleSwitch

from tiebashelf.spider.utils import normalize_url
from tiebashelf.spider.index_manage import IndexManager
from tiebashelf.ui.pages.widgets.async_worker import AsyncWorker

# === 核心界面类 ===
class PageCrawl(QWidget):
    """爬取功能页面，提供帖子 URL 批量输入、校验、去重和异步爬取"""

    def __init__(self, spider_instance=None, main_window=None):
        super().__init__()
        self.main_window = main_window
        self.spider = spider_instance  # 爬虫实例，外部传入
        self.worker_thread = None      # 统一管理工作线程，避免多线程混乱
        self.worker = None             # 统一管理工作实例
        self.index_manager = IndexManager()
        self.progress_mgr = main_window.global_progress_mgr if main_window else None # 引用全局管理器
        self.is_task_running = False  # 全局任务锁
        self._cleanup_done = False    # 防止重复清理
        self.init_ui()

    def init_ui(self):
        """初始化 UI 布局，纯可视化逻辑，无业务侵入"""
        layout = QVBoxLayout()

        # === 标题 ===
        title = QLabel("【爬取功能区】")
        title.setStyleSheet("font-weight: bold; font-size: 14px;color: #333333;")
        layout.addWidget(title)

        # === URL 输入框（多行） ===
        self.url_input = QTextEdit()
        self.url_input.setPlaceholderText(
            "请输入贴吧帖子链接，每行一个，支持批量输入：\n"
            "https://tieba.baidu.com/p/1234567890\n"
            "https://tieba.baidu.com/p/9876543210?see_lz=1"
        )
        self.url_input.setReadOnly(False)
        layout.addWidget(self.url_input)

        # === 选项行：只看楼主 ===
        options_layout = QHBoxLayout()
        self.see_lz_switch = ToggleSwitch()
        lz_label = QLabel("只看楼主")
        lz_label.setStyleSheet("""
            QLabel {
            font-size: 13px;
            color: #333333;
            }
            """)
        lz_label.setToolTip("开启后只爬取楼主发布的楼层")
        options_layout.addWidget(self.see_lz_switch)
        options_layout.addWidget(lz_label)
        options_layout.addStretch()
        layout.addLayout(options_layout)

        # === 按钮行 ===
        button_layout = QHBoxLayout()
        self.start_button = QPushButton("开始爬取")
        self.clear_button = QPushButton("清空输入")
        self.test_button = QPushButton("测试 URL")

        self.start_button.clicked.connect(self.start_crawl)
        self.clear_button.clicked.connect(self.clear_input)
        self.test_button.clicked.connect(self.test_urls)

        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.clear_button)
        button_layout.addWidget(self.test_button)
        layout.addLayout(button_layout)

        # === 状态显示 ===
        self.status_label = QLabel("时刻准备着...")
        self.status_label.setStyleSheet("color: gray; font-size: 12px;")
        layout.addWidget(self.status_label)

        # === 分隔线 ===
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(line)

        # === 底部说明 ===
        hint = QLabel("提示：支持批量粘贴 URL，一行一个，自动过滤重复和无效链接，暂不支持爬取楼中楼回复")
        hint.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(hint)

        layout.addStretch()
        self.setLayout(layout)

    # === 核心业务逻辑 ===
    def start_crawl(self):
        """开始爬取主入口：URL 校验→归一化→去重→用户选择→任务执行"""
        try:
            # 1. 空输入校验
            urls_text = self.url_input.toPlainText().strip()
            if not urls_text:
                QMessageBox.warning(self, "输入错误", "请输入至少一个 URL！")
                return

            # 2. 获取用户配置
            see_lz = self.see_lz_switch.isChecked()

            # 3. 解析 URL（过滤空行）
            raw_urls = [line.strip() for line in urls_text.split('\n') if line.strip()]

            # 4. URL 归一化 + 无效链接过滤
            normalized_urls, invalid_urls = self.normalize_and_filter_urls(raw_urls, see_lz)

            # 5. 无效链接提示
            if invalid_urls:
                self.show_invalid_url_warning(invalid_urls)

            # 6. 无有效链接直接返回
            if not normalized_urls:
                QMessageBox.information(self, "无有效链接", "没有找到有效的贴吧帖子链接。")
                return

            # 7. 重复链接检测
            unique_urls, duplicate_urls = self.check_duplicate_urls(normalized_urls, see_lz)

            # 8. 处理链接（无重复时直接爬新链接）
            if duplicate_urls:
                self.handle_duplicate_urls(duplicate_urls, unique_urls)
            else:
                self.start_async_crawl(new_urls=unique_urls)

            # 9. 清空输入框
            self.clear_input()
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            QMessageBox.critical(self, "错误", f"发生错误：{str(e)}\n\n详细信息：\n{error_detail}")

    def normalize_and_filter_urls(self, raw_urls, see_lz):
        """URL 归一化 + 无效链接过滤

        Args:
            raw_urls: 原始 URL 列表
            see_lz: 是否只看楼主

        Returns:
            (有效 URL 列表, 无效 URL 列表)
        """
        normalized_urls = []
        invalid_urls = []
        for url in raw_urls:
            normalized = normalize_url(url, see_lz=see_lz)
            if normalized:
                normalized_urls.append(normalized)
            else:
                invalid_urls.append(url)
        return normalized_urls, invalid_urls

    def show_invalid_url_warning(self, invalid_urls):
        """统一显示无效链接提示"""
        invalid_str = '\n'.join(invalid_urls[:5])
        if len(invalid_urls) > 5:
            invalid_str += f"\n... 还有 {len(invalid_urls) - 5} 个无效链接"
        QMessageBox.warning(self, "无效链接", f"以下链接格式不正确：\n{invalid_str}")

    def check_duplicate_urls(self, normalized_urls, see_lz):
        """与索引对比检测重复链接

        Args:
            normalized_urls: 已归一化的 URL 列表
            see_lz: 是否只看楼主

        Returns:
            (新 URL 列表, 重复 URL 列表)
        """
        unique_urls = []
        duplicate_urls = []
        for url in normalized_urls:
            duplicate_status = self.index_manager.check_repeated_url(url, see_lz=see_lz)
            if duplicate_status == "new":
                unique_urls.append(url)
            elif duplicate_status == "same":
                duplicate_urls.append(url)
        return list(set(unique_urls)), list(set(duplicate_urls))

    def handle_duplicate_urls(self, duplicate_urls, unique_urls):
        """弹出重复链接处理对话框，让用户选择跳过或更新

        Args:
            duplicate_urls: 已存在的重复链接列表
            unique_urls: 新发现的链接列表
        """
        dialog = DuplicateHandlingDialog(duplicate_urls, len(unique_urls), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            user_choice = dialog._user_choice
            try:
                if user_choice == "skip":
                    if not unique_urls:
                        QMessageBox.information(self, "无新链接", "没有新链接需要处理。")
                        return
                    self.start_async_crawl(new_urls=unique_urls)
                elif user_choice == "update":
                    self.start_async_crawl(
                        new_urls=unique_urls,
                        update_urls=duplicate_urls,
                    )
            except Exception as e:
                import traceback
                error_detail = traceback.format_exc()
                QMessageBox.critical(self, "报错详情", f"错误类型：{type(e).__name__}\n错误信息：{str(e)}\n\n完整栈：\n{error_detail}")

    # === 异步任务管理 ===
    def start_async_crawl(self, new_urls=None, update_urls=None):
        """启动异步任务"""
        try:
            asyncio.set_event_loop(asyncio.new_event_loop())
            self._cleanup_done = False  # 重置清理标志
            
            # 先清理旧的（如果有）
            if self.worker_thread and self.worker_thread.isRunning():
                self.worker_thread.quit()
                self.worker_thread.wait(1000)  # 带超时等待
            self.worker_thread = None
            self.worker = None
            self.is_task_running = False

            new_urls = new_urls or []
            update_urls = update_urls or []
            total = len(new_urls) + len(update_urls)

            if total == 0:
                return

            # === 启动进度管理 ===
            self.is_task_running = True
            self.progress_mgr.start_task(total_items=total, current_page=self)

            # === 创建线程 ===
            self.worker_thread = QThread()
            self.worker = AsyncWorker(new_urls, update_urls)
            self.worker.moveToThread(self.worker_thread)

            # === 连接信号 ===
            self.worker_thread.started.connect(self.worker.run_async_task)
            self.worker.finished.connect(self.on_crawl_finished)
            self.worker.error.connect(self.on_crawl_error)
            self.worker.task_completed.connect(self._on_task_completed)

            # 启动任务并更新状态
            self.worker_thread.start()
            self.status_label.setText(
                f"处理中（总{total}个）：新帖{len(new_urls)}个，更新{len(update_urls)}个"
            )
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            QMessageBox.critical(self, "错误", f"启动爬取任务失败：{str(e)}\n\n详细信息：\n{error_detail}")

    # === 回调函数 ===
    def on_crawl_finished(self, results):
        """任务完成回调：先恢复 UI，再延迟显示对话框"""
        # 1. 先恢复 UI 控件状态
        self.start_button.setEnabled(True)
        self.test_button.setEnabled(True)
        self.url_input.setReadOnly(False)

        # 2. 统计结果
        success_count = sum(1 for r in results if r['status'] in ['success', 'updated'])
        error_count = sum(1 for r in results if r['status'] == 'error')
        skip_count = len(results) - success_count - error_count
        self.status_label.setText(f"完成！成功：{success_count}, 失败：{error_count}, 跳过：{skip_count}")

        # 3. 延迟清理和显示对话框
        # 使用 QTimer 确保在事件循环的下一次迭代中执行，避免线程清理冲突
        QTimer.singleShot(0, lambda: self._finish_and_show_dialog(success_count, error_count, skip_count))

    def _finish_and_show_dialog(self, success_count, error_count, skip_count):
        """完成清理并显示对话框"""
        if self._cleanup_done:
            return
        self._cleanup_done = True
        
        # 清理工作线程
        self._cleanup_worker_no_wait()
        
        # 完成进度管理
        self.is_task_running = False
        if self.progress_mgr:
            self.progress_mgr.finish_all()

        if success_count > 0 and self.main_window and hasattr(self.main_window, '_refresh_manage_page'):
            self.main_window._refresh_manage_page()

        # 显示对话框
        QMessageBox.information(
            self, "完成",
            f"批量处理完成！\n成功：{success_count}\n失败：{error_count}\n跳过：{skip_count}"
        )

    def on_crawl_error(self, error_msg):
        """异步任务出错回调：恢复 UI 并显示错误对话框

        Args:
            error_msg: 错误信息
        """
        # 1. 恢复 UI
        self.start_button.setEnabled(True)
        self.test_button.setEnabled(True)
        self.url_input.setReadOnly(False)
        self.status_label.setText("发生错误")

        # 2. 延迟显示错误对话框
        QTimer.singleShot(0, lambda: self._finish_and_show_error(error_msg))

    def _finish_and_show_error(self, error_msg):
        """完成清理并显示错误对话框"""
        if self._cleanup_done:
            return
        self._cleanup_done = True
        
        # 清理工作线程（不阻塞）
        self._cleanup_worker_no_wait()
        
        # 完成进度管理
        self.is_task_running = False
        if self.progress_mgr:
            self.progress_mgr.finish_all()
        
        # 显示错误对话框
        QMessageBox.critical(self, "错误", f"爬取过程中发生错误：\n{error_msg}")

    def _cleanup_worker_no_wait(self):
        """非阻塞清理工作线程（关键修复：避免 wait() 阻塞 UI 线程）"""
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.quit()
            self.worker_thread.deleteLater()
        self.worker_thread = None
        self.worker = None

    def on_crawl_progress(self, message):
        """进度更新回调"""
        self.status_label.setText(message)

    # === 基础 UI 功能 ===
    def clear_input(self):
        """清空输入框"""
        self.url_input.clear()
        self.status_label.setText("时刻准备着...")
        self.status_label.setStyleSheet("color: gray; font-size: 12px;")

    def _on_task_completed(self, url: str, task_type: str):
        """每个 URL 任务完成时调用"""
        self.progress_mgr.update_item(task_type)

    def on_task_finish(self, original_states):
        """任务结束时：根据原始状态恢复控件"""
        self.start_button.setEnabled(original_states["start_button"])
        self.test_button.setEnabled(original_states["test_button"])
        self.see_lz_switch.setEnabled(original_states["see_lz_switch"])
        self.url_input.setReadOnly(original_states["url_input"])

    def on_task_start(self):
        """任务开始时：记录控件原始状态，并禁用关键按钮"""
        original_states = {
            "start_button": self.start_button.isEnabled(),
            "test_button": self.test_button.isEnabled(),
            "see_lz_switch": self.see_lz_switch.isEnabled(),
            "url_input": self.url_input.isReadOnly()
        }
        self.start_button.setEnabled(False)
        self.test_button.setEnabled(False)
        self.see_lz_switch.setEnabled(False)
        self.url_input.setReadOnly(True)
        return original_states

    def test_urls(self):
        """批量测试 URL 格式有效性"""
        urls_text = self.url_input.toPlainText().strip()
        if not urls_text:
            QMessageBox.information(self, "提示", "请先输入一些 URL 进行测试。")
            return

        raw_urls = [line.strip() for line in urls_text.split('\n') if line.strip()]
        valid_count = sum(1 for url in raw_urls if self.is_valid_tieba_url(url))

        QMessageBox.information(
            self, "测试结果",
            f"总链接数：{len(raw_urls)}\n有效链接：{valid_count}\n无效链接：{len(raw_urls) - valid_count}"
        )

    def is_valid_tieba_url(self, url: str) -> bool:
        """校验贴吧帖子 URL 格式

        Args:
            url: 待校验的 URL

        Returns:
            True 为有效贴吧链接
        """
        pattern = r'^https://tieba\.baidu\.com/p/\d+(?:\?.*)?$'
        return bool(re.match(pattern, url.strip()))


# === 辅助类：重复链接对话框 ===
class DuplicateHandlingDialog(QDialog):
    """自定义重复链接处理对话框"""
    def __init__(self, duplicate_urls, unique_count, parent=None):
        super().__init__(parent)
        self._user_choice: str | None = None
        self.setWindowTitle("重复链接处理")
        self.setModal(True)
        self.init_ui(duplicate_urls, unique_count)

    def init_ui(self, duplicate_urls, unique_count):
        """初始化对话框布局

        Args:
            duplicate_urls: 重复链接列表
            unique_count: 新链接数量
        """
        layout = QVBoxLayout()

        urls_text = '\n'.join(duplicate_urls[:5]) if len(duplicate_urls) <= 5 else \
            '\n'.join(duplicate_urls[:5]) + f"\n... 还有 {len(duplicate_urls) - 5} 个"
        message = (
            f"发现 {len(duplicate_urls)} 个重复链接：\n{urls_text}\n\n"
            f"共 {unique_count} 个新链接。\n请选择如何处理重复链接："
        )
        label = QLabel(message)
        label.setWordWrap(True)
        layout.addWidget(label)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(line)

        button_layout = QHBoxLayout()
        skip_btn = QPushButton("忽略跳过")
        update_btn = QPushButton("更新爬取")
        cancel_btn = QPushButton("终止所有爬取")

        skip_btn.clicked.connect(self.on_skip)
        update_btn.clicked.connect(self.on_update)
        cancel_btn.clicked.connect(self.reject)

        button_layout.addWidget(skip_btn)
        button_layout.addWidget(update_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def on_skip(self):
        """用户选择跳过重复链接"""
        self._user_choice = "skip"
        self.accept()

    def on_update(self):
        """用户选择重新爬取更新重复链接"""
        self._user_choice = "update"
        self.accept()
