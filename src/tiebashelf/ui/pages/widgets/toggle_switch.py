from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Signal, Qt, QPropertyAnimation, QEasingCurve, Property, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush

class ToggleSwitch(QWidget):
    toggled = Signal(bool)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(40, 22)
        self._checked = False
        self._offset = 0  # 私有变量，存储offset的实际值
        
        # 直接使用注册后的"offset"属性，Qt可识别，无报错
        self._animation = QPropertyAnimation(self, b"offset", self)
        self._animation.setDuration(200)
        self._animation.setEasingCurve(QEasingCurve.Type.OutQuad)
    
    # PySide6 Property：getter/setter 显式命名，避免 decorator 混淆
    def _get_offset(self) -> float:
        return self._offset

    def _set_offset(self, value: float):
        self._offset = value
        self.update()

    offset = Property(float, _get_offset, _set_offset)
    
    def isChecked(self):
        return self._checked
        
    def setChecked(self, checked):
        if self._checked != checked:
            self._checked = checked
            end_value = 20 if checked else 2
            self._animation.stop()
            self._animation.setStartValue(self._offset)
            self._animation.setEndValue(end_value)
            self._animation.start()
            self.toggled.emit(checked)
            
    def mousePressEvent(self, event):
        self.setChecked(not self._checked)
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # === 滑轨（Track）绘制 ===
        track_width = self.width()      # 40
        track_height = self.height()    # 22
        corner_radius = track_height // 2  # 11 → 完全圆角
        
        # 背景颜色（根据状态）
        bg_color = QColor(155, 205, 246) if self._checked else QColor(200, 200, 200)
   
        # 画内填充（覆盖边框内部）
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bg_color))
        # 缩小矩形以避开边框（内缩 1.5px，因为边框宽3px，每边占1.5px）
        inner_rect = QRectF(1.5, 1.5, track_width - 3, track_height - 3)
        painter.drawRoundedRect(inner_rect, corner_radius - 1.5, corner_radius - 1.5)
        
        # === 滑块（Thumb）绘制 ===
        thumb_size = 18  
        # 滑块位置：在 2px 到 (40 - 18 - 2) = 20px 之间滑动
        
        thumb_x = int(self._offset)
        thumb_y = (track_height - thumb_size) // 2  # 垂直居中：(22-18)/2 = 2
        
        # 白色滑块 + 可选轻微阴影边框
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.setPen(QPen(QColor(180, 180, 180), 1))  # 浅灰细边框，增强立体感
        painter.drawEllipse(thumb_x, thumb_y, thumb_size, thumb_size)