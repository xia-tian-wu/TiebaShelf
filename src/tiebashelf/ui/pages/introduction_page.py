from PySide6.QtWidgets import QTextBrowser, QVBoxLayout, QWidget
from tiebashelf.config import PACKAGE_DIR

class PageFuture(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)  # 适配QT控件内边距
        layout.setSpacing(0)
        
        # 创建富文本浏览器
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)  # 自动打开超链接
        browser.setReadOnly(True)
        browser.setStyleSheet("""
            QTextBrowser {
                background-color: #f5f7fa;  /* 全局淡蓝灰色背景 */
                font-size: 14px;
                line-height: 1.6;
                color: #333;
                border: none;  /* 移除默认边框 */
                padding: 5px;
            }
            QTextBrowser a {
                color: #3498db;  /* 超链接颜色 */
                text-decoration: none;
            }
            QTextBrowser a:hover {
                color: #2980b9;
                text-decoration: underline;
            }
        """)
        
        # 设置 HTML 内容
        html_content = self._load_html_content()
        
        browser.setHtml(html_content)
        layout.addWidget(browser)
    
    def _load_html_content(self) -> str:
        html_path = PACKAGE_DIR / 'ui' / 'pages' / 'introduction.html'
        with open(html_path, 'r', encoding='utf-8') as f:
            return f.read()