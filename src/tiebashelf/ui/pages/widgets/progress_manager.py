from PySide6.QtWidgets import QProgressBar, QLabel
from PySide6.QtCore import Qt

class TaskProgressManager:
    def __init__(self, status_label, progress_bar):
        self.status_label = status_label
        self.progress_bar = progress_bar
        self._total_count = 0
        self._current_count = 0
        self._last_task_type = "default"
        self.TASK_TYPE_LABELS = {
            "crawl": "爬取新帖",
            "update": "更新旧帖",
            "recrawl":"重新爬取",
            "delete":"删除帖子",
            "default": "处理中"
        }
        self.current_page = None
        self.page_states = {} # 格式: {页面实例: {控件: 原状态}}
        self.hide()

    def start_task(self, total_items: int, current_page=None):
        """启动任务时记录当前界面，并禁用其控件"""
        self.progress_bar.setRange(0, total_items)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%v/%m")

        self._total_count = total_items
        self._current_count = 0
        self._last_task_type = "default"
        self.current_page = current_page
        self.show()
        self._update_ui()
        if hasattr(current_page, 'on_task_start'):
            self.page_states[current_page] = current_page.on_task_start()

    def update_item(self, task_type: str = "default"):
        self._last_task_type = task_type
        self._current_count = min(self._current_count + 1, self._total_count)
        self._update_ui()

    def _update_ui(self):
        label = self.TASK_TYPE_LABELS.get(self._last_task_type, "处理中")
        text = f"{label} ({self._current_count}/{self._total_count})"
        self.status_label.setText(text)
        
        if self._total_count > 0:
            # 进度条范围设为总数量，值为当前数量
            self.progress_bar.setRange(0, self._total_count)
            self.progress_bar.setValue(self._current_count)
            self.progress_bar.setFormat("%v/%m")  # 显示"5/7"格式
        self.progress_bar.show()

    def show(self):
        self.progress_bar.show()
        self.status_label.show()
        self.status_label.setStyleSheet("color: #4E4F52; font-weight: bold;")
        
    def finish_all(self):
        """任务完全结束,任务结束时恢复页面控件状态，重置计数"""
        self._total_count = 0
        self._current_count = 0
        self._last_task_type = "default"
        self.status_label.setText("就绪")
        self.hide()
        if self.current_page and self.current_page in self.page_states:
            if hasattr(self.current_page, 'on_task_finish'):
                self.current_page.on_task_finish(self.page_states[self.current_page])
            del self.page_states[self.current_page]
        self.current_page = None

    def hide(self):
        self.progress_bar.hide()
        self.status_label.hide()