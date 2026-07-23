"""Widget that renders application backgrounds in stretched or cover mode."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QPaintEvent, QPainter, QPixmap, QResizeEvent
from PySide6.QtWidgets import QWidget


class CoverBackgroundWidget(QWidget):
    """Paint a background image behind child widgets."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._background = QPixmap(":/ui/images/bg.png")
        self._background_mode = "stretched"
        self._scaled_background = QPixmap()
        self._update_scaled_background()

    def set_background(self, file_path: str | None, mode: str) -> None:
        """Set the image and rendering mode used for the application background."""
        background = QPixmap(file_path or ":/ui/images/bg.png")
        if not background.isNull():
            self._background = background

        self._background_mode = mode
        self._update_scaled_background()
        self.update()

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Recalculate the rendered background when the window size changes."""
        super().resizeEvent(event)
        self._update_scaled_background()

    def paintEvent(self, _event: QPaintEvent) -> None:
        """Draw the scaled background centered in the available area."""
        if self._scaled_background.isNull():
            return

        x = (self.width() - self._scaled_background.width()) // 2
        y = (self.height() - self._scaled_background.height()) // 2

        painter = QPainter(self)
        painter.drawPixmap(x, y, self._scaled_background)

    def _update_scaled_background(self) -> None:
        """Scale the selected image for the widget's current size."""
        if self.size().isEmpty() or self._background.isNull():
            self._scaled_background = QPixmap()
            return

        aspect_ratio_mode = (
            Qt.AspectRatioMode.KeepAspectRatioByExpanding
            if self._background_mode == "cropped"
            else Qt.AspectRatioMode.IgnoreAspectRatio
        )
        self._scaled_background = self._background.scaled(
            self.size(),
            aspect_ratio_mode,
            Qt.TransformationMode.SmoothTransformation,
        )
