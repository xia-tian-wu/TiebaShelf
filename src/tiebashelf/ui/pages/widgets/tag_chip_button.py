from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Signal, Qt, QRectF, QSize
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFontMetrics, QPainterPath


class TagChipButton(QWidget):
    """交互式胶囊标签：左文字（点击复制） + 右✕（点击删除），QPainter 自绘"""
    clicked = Signal(str)
    delete_clicked = Signal(str)

    DEL_WIDTH = 24

    COLOR_BG = QColor(216, 220, 227)       # #d8dce3
    COLOR_BORDER = QColor(192, 196, 203)   # #c0c4cb
    COLOR_HOVER_LEFT = QColor(74, 144, 217)   # #4a90d9
    COLOR_HOVER_RIGHT = QColor(217, 74, 74)   # #d94a4a
    COLOR_TEXT = QColor(51, 51, 51)        # #333
    COLOR_TEXT_HOVER = QColor(255, 255, 255)  # white

    def __init__(self, tag: str, parent=None):
        super().__init__(parent)
        self.tag = tag
        self.setFixedHeight(24)
        self.setMouseTracking(True)
        self._hover_left = False
        self._hover_right = False

    def sizeHint(self):
        fm = QFontMetrics(self.font())
        text_w = fm.horizontalAdvance(self.tag)
        total_w = 10 + text_w + 4 + self.DEL_WIDTH
        return QSize(total_w, 24)

    # ── 事件 ──

    def _right_area_x(self) -> int:
        return self.width() - self.DEL_WIDTH

    def _is_right_area(self, x: int) -> bool:
        return x >= self._right_area_x()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._is_right_area(event.position().toPoint().x()):
                self.delete_clicked.emit(self.tag)
            else:
                self.clicked.emit(self.tag)

    def mouseMoveEvent(self, event):
        right = self._is_right_area(int(event.position().x()))
        old_left, old_right = self._hover_left, self._hover_right
        self._hover_left = not right
        self._hover_right = right
        if old_left != self._hover_left or old_right != self._hover_right:
            self.update()

    def enterEvent(self, event):
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def leaveEvent(self, event):
        self._hover_left = False
        self._hover_right = False
        self.update()

    # ── 绘制 ──

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        w = self.width()
        h = self.height()
        r = h // 2
        rx = self._right_area_x()

        rect = QRectF(0.5, 0.5, w - 1, h - 1)

        # 胶囊背景 + 边框
        painter.setBrush(QBrush(self.COLOR_BG))
        painter.setPen(QPen(self.COLOR_BORDER, 1))
        painter.drawRoundedRect(rect, r - 0.5, r - 0.5)

        # 左半 hover
        if self._hover_left:
            path = QPainterPath()
            path.moveTo(0, h)
            path.lineTo(0, 0)
            path.lineTo(rx, 0)
            path.lineTo(rx, h)
            path.closeSubpath()
            painter.setClipPath(path)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(self.COLOR_HOVER_LEFT))
            painter.drawRoundedRect(rect, r - 0.5, r - 0.5)
            painter.setClipping(False)

        # 右半 hover
        if self._hover_right:
            path = QPainterPath()
            path.moveTo(rx, 0)
            path.lineTo(rx, h)
            path.lineTo(w, h)
            path.lineTo(w, 0)
            path.closeSubpath()
            painter.setClipPath(path)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(self.COLOR_HOVER_RIGHT))
            painter.drawRoundedRect(rect, r - 0.5, r - 0.5)
            painter.setClipping(False)

        # 文字
        text_color = self.COLOR_TEXT_HOVER if self._hover_left else self.COLOR_TEXT
        painter.setPen(text_color)
        text_rect = QRectF(0, 0, rx, h)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self.tag)

        # ✕
        x_color = self.COLOR_TEXT_HOVER if self._hover_right else self.COLOR_TEXT
        painter.setPen(x_color)
        x_rect = QRectF(rx, 0, self.DEL_WIDTH, h)
        painter.drawText(x_rect, Qt.AlignmentFlag.AlignCenter, "✕")
