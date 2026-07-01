# logger.py
import logging
import sys
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QTextEdit
from PySide6.QtGui import QTextCursor

# 自定义UI日志处理器（线程安全）
class QTextEditLogHandler(logging.Handler, QObject):
    # 定义信号：用于跨线程传递日志文本（PySide6 UI操作必须在主线程）
    log_signal = Signal(str)

    def __init__(self, text_edit: QTextEdit):
        logging.Handler.__init__(self)
        QObject.__init__(self)
        self.text_edit = text_edit
        # 绑定信号到UI更新函数
        self.log_signal.connect(self._update_log_ui)

    def emit(self, record):
        """重写emit方法：将日志转为字符串，通过信号发送到主线程"""
        try:
            # 用当前handler的格式器格式化日志
            msg = self.format(record)
            # 发送信号（即使在异步线程，signal会自动切换到主线程）
            self.log_signal.emit(msg)
        except Exception:
            self.handleError(record)

    def _update_log_ui(self, msg: str):
        """主线程执行：更新QTextEdit日志区域"""
        self.text_edit.append(msg)
        # 自动滚动到最新日志行
        cursor = self.text_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.text_edit.setTextCursor(cursor)

def setup_logger(name: str = "tieba_spider", level=logging.INFO) -> logging.Logger:
    """配置统一的日志器（保留原有逻辑）"""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # 避免重复添加 handler

    logger.setLevel(level)
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    
    # 设置日志格式
    formatter = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-8s | %(filename)s | %(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(formatter)
    
    logger.addHandler(console_handler)
    logger.propagate = False  # 防止日志传播到 root logger
    
    return logger

# 新增：给全局logger添加UI日志处理器的便捷函数
def add_ui_handler(text_edit: QTextEdit, level=logging.INFO):
    """
    给全局logger绑定UI日志输出

    Args:
        text_edit: 日志显示的QTextEdit组件
        level: 日志级别

    Returns:
        新增的UI处理器（方便后续移除）
    """
    logger = logging.getLogger("tieba_spider")
    # 创建UI处理器
    ui_handler = QTextEditLogHandler(text_edit)
    ui_handler.setLevel(level)
    
    # 自定义UI日志格式（可简化，避免UI显示过于拥挤）
    ui_formatter = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-8s | %(message)s',  # 简化funcName/lineno
        datefmt='%H:%M:%S'  # UI只显示时分秒，更简洁
    )
    ui_handler.setFormatter(ui_formatter)
    
    # 添加到logger
    logger.addHandler(ui_handler)
    return ui_handler

# 移除UI日志处理器（避免内存泄漏）
def remove_ui_handler(ui_handler: QTextEditLogHandler):
    logger = logging.getLogger("tieba_spider")
    if ui_handler in logger.handlers:
        logger.removeHandler(ui_handler)

# 全局日志实例（供其他模块导入）
logger: logging.Logger = setup_logger()