"""Inline stretch and ratio-constrained crop controls for image previews."""

from __future__ import annotations

from itertools import count
import logging
from pathlib import Path
from typing import Callable, Optional

from PIL import Image, ImageOps
from PySide6.QtCore import (
    QDir,
    QEvent,
    QLineF,
    QObject,
    QPointF,
    QRectF,
    Qt,
    QTemporaryDir,
    Signal,
)
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QMessageBox,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)
_IMAGE_TEMP_DIR = QTemporaryDir(f"{QDir.tempPath()}/floowandereeze-images-XXXXXX")
_IMAGE_SEQUENCE = count()


class CropPreview(QWidget):
    """Paint and manipulate a ratio-locked crop over a preview image."""

    crop_committed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = QPixmap()
        self._aspect_ratio = 1.0
        self._crop = QRectF()
        self._drag_offset: Optional[QPointF] = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip("Drag to reposition the crop. Use the mouse wheel to zoom.")

    def set_source(self, image_path: str, target_size: tuple[int, int]) -> None:
        """Load a source image and reset its crop to the largest target ratio."""
        self._pixmap = QPixmap(image_path)
        self._aspect_ratio = target_size[0] / target_size[1]
        self._crop = self._largest_crop()
        self.update()

    def crop_box(self) -> tuple[int, int, int, int]:
        """Return the selected crop in source-image coordinates."""
        return (
            round(self._crop.left()),
            round(self._crop.top()),
            round(self._crop.right()),
            round(self._crop.bottom()),
        )

    def _largest_crop(self) -> QRectF:
        width = float(self._pixmap.width())
        height = float(self._pixmap.height())
        if width <= 0 or height <= 0:
            return QRectF()
        if width / height > self._aspect_ratio:
            crop_width = height * self._aspect_ratio
            return QRectF((width - crop_width) / 2, 0, crop_width, height)
        crop_height = width / self._aspect_ratio
        return QRectF(0, (height - crop_height) / 2, width, crop_height)

    def _image_rect(self) -> QRectF:
        if self._pixmap.isNull():
            return QRectF()
        scaled = self._pixmap.size()
        scaled.scale(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        return QRectF(
            (self.width() - scaled.width()) / 2,
            (self.height() - scaled.height()) / 2,
            scaled.width(),
            scaled.height(),
        )

    def _source_to_widget(self, rect: QRectF) -> QRectF:
        image_rect = self._image_rect()
        if image_rect.width() <= 0:
            return QRectF()
        scale = image_rect.width() / self._pixmap.width()
        return QRectF(
            image_rect.left() + rect.left() * scale,
            image_rect.top() + rect.top() * scale,
            rect.width() * scale,
            rect.height() * scale,
        )

    def _widget_to_source(self, point: QPointF) -> QPointF:
        image_rect = self._image_rect()
        if image_rect.width() <= 0:
            return QPointF()
        scale = self._pixmap.width() / image_rect.width()
        return QPointF(
            (point.x() - image_rect.left()) * scale,
            (point.y() - image_rect.top()) * scale,
        )

    def _clamp_crop(self) -> None:
        left = min(
            max(0.0, self._crop.left()), self._pixmap.width() - self._crop.width()
        )
        top = min(
            max(0.0, self._crop.top()), self._pixmap.height() - self._crop.height()
        )
        self._crop.moveTopLeft(QPointF(left, top))

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor("#202020"))
        image_rect = self._image_rect()
        painter.drawPixmap(image_rect.toRect(), self._pixmap)

        crop_rect = self._source_to_widget(self._crop)
        painter.save()
        painter.setClipRect(image_rect)
        painter.setBrush(QColor(0, 0, 0, 155))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(image_rect)
        painter.restore()
        painter.drawPixmap(crop_rect, self._pixmap, self._crop)

        painter.setPen(QPen(QColor("#ffffff"), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(crop_rect)
        painter.setPen(QPen(QColor(255, 255, 255, 150), 1))
        for fraction in (1 / 3, 2 / 3):
            painter.drawLine(
                QLineF(
                    crop_rect.left() + crop_rect.width() * fraction,
                    crop_rect.top(),
                    crop_rect.left() + crop_rect.width() * fraction,
                    crop_rect.bottom(),
                )
            )
            painter.drawLine(
                QLineF(
                    crop_rect.left(),
                    crop_rect.top() + crop_rect.height() * fraction,
                    crop_rect.right(),
                    crop_rect.top() + crop_rect.height() * fraction,
                )
            )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        source_point = self._widget_to_source(event.position())
        if event.button() == Qt.MouseButton.LeftButton and self._crop.contains(
            source_point
        ):
            self._drag_offset = source_point - self._crop.topLeft()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is None:
            return
        self._crop.moveTopLeft(
            self._widget_to_source(event.position()) - self._drag_offset
        )
        self._clamp_crop()
        self.update()

    def mouseReleaseEvent(self, _event: QMouseEvent) -> None:
        if self._drag_offset is not None:
            self._drag_offset = None
            self.crop_committed.emit()
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self._crop.isEmpty():
            return
        largest = self._largest_crop()
        direction = -1 if event.angleDelta().y() > 0 else 1
        new_width = self._crop.width() * (1 + direction * 0.08)
        new_width = min(largest.width(), max(largest.width() * 0.1, new_width))
        new_height = new_width / self._aspect_ratio
        center = self._crop.center()
        self._crop = QRectF(
            center.x() - new_width / 2,
            center.y() - new_height / 2,
            new_width,
            new_height,
        )
        self._clamp_crop()
        self.update()
        self.crop_committed.emit()
        event.accept()


# pylint: disable-next=too-many-instance-attributes
class InlineImageFitController(QObject):
    """Add fit buttons below a preview and prepare its replacement image."""

    def __init__(
        self,
        page: QWidget,
        preview: QWidget,
        target_size: tuple[int, int] | Callable[[], tuple[int, int]],
        image_ready: Callable[[str], None],
        alignment_widget: Optional[QWidget] = None,
    ):
        super().__init__(page)
        self._page = page
        self._preview = preview
        self._target_size = target_size
        self._image_ready = image_ready
        self._alignment_widget = alignment_widget
        self._source_image: Optional[Image.Image] = None
        self._source_path: Optional[str] = None

        self._add_inline_controls()
        self._balance_alignment_column()
        self._crop_preview = CropPreview(preview)
        self._crop_preview.hide()
        self._crop_preview.crop_committed.connect(self._render_output)
        preview.installEventFilter(self)

    def _add_inline_controls(self) -> None:
        layout, index = self._find_widget_layout(self._page.layout(), self._preview)
        if layout is None:
            raise ValueError("Preview widget is not managed by the page layout")

        item = layout.itemAt(index)
        alignment = item.alignment()
        stretch = layout.stretch(index) if hasattr(layout, "stretch") else 0
        layout.takeAt(index)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        container = QWidget(self._page)
        container.setObjectName(f"{self._preview.objectName()}FitContainer")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(6)
        preview_alignment = (
            alignment
            if alignment
            else Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
        )
        container_layout.addWidget(self._preview, 1, preview_alignment)

        buttons_layout = QHBoxLayout()
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(6)
        self.stretch_button = QRadioButton("Stretch", container)
        self.stretch_button.setObjectName(f"{self._preview.objectName()}StretchButton")
        self.stretch_button.setChecked(True)
        self.stretch_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stretch_button.setToolTip("Stretch the source image to fill the asset.")
        self.crop_button = QRadioButton("Crop", container)
        self.crop_button.setObjectName(f"{self._preview.objectName()}CropButton")
        self.crop_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.crop_button.setToolTip(
            "Preserve proportions. Drag the preview to move the crop and "
            "use the mouse wheel to zoom."
        )

        self._button_group = QButtonGroup(container)
        self._button_group.setExclusive(True)
        self._button_group.addButton(self.stretch_button)
        self._button_group.addButton(self.crop_button)
        buttons_layout.addStretch(1)
        buttons_layout.addWidget(self.stretch_button)
        buttons_layout.addWidget(self.crop_button)
        buttons_layout.addStretch(1)
        container_layout.addLayout(buttons_layout)

        self.stretch_button.setEnabled(False)
        self.crop_button.setEnabled(False)
        self.stretch_button.toggled.connect(self._fit_mode_changed)
        layout.insertWidget(index, container, stretch, alignment)

    def _balance_alignment_column(self) -> None:
        """Reserve the fit-control row beneath a paired current image."""
        if self._alignment_widget is None:
            return
        layout, index = self._find_widget_layout(
            self._page.layout(), self._alignment_widget
        )
        if layout is None:
            return
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        spacer = QWidget(self._page)
        spacer.setObjectName(f"{self._alignment_widget.objectName()}FitRowSpacer")
        spacer.setFixedHeight(
            max(
                self.stretch_button.sizeHint().height(),
                self.crop_button.sizeHint().height(),
            )
        )
        layout.insertWidget(index + 1, spacer)

    @classmethod
    def _find_widget_layout(cls, layout, widget):
        if layout is None:
            return None, -1
        for index in range(layout.count()):
            item = layout.itemAt(index)
            if item.widget() is widget:
                return layout, index
            nested_layout = item.layout()
            if nested_layout:
                found_layout, found_index = cls._find_widget_layout(
                    nested_layout, widget
                )
                if found_layout is not None:
                    return found_layout, found_index
            child_widget = item.widget()
            if child_widget and child_widget.layout():
                found_layout, found_index = cls._find_widget_layout(
                    child_widget.layout(), widget
                )
                if found_layout is not None:
                    return found_layout, found_index
        return None, -1

    def eventFilter(self, watched, event) -> bool:
        if watched is self._preview and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Show,
        ):
            self._crop_preview.setGeometry(self._preview.rect())
            self._crop_preview.raise_()
        return super().eventFilter(watched, event)

    def set_source(self, image_path: str) -> bool:
        """Load a source and immediately render it using the selected fit mode."""
        target_size = self._current_target_size()
        if target_size[0] <= 0 or target_size[1] <= 0:
            return False
        try:
            with Image.open(image_path) as opened_image:
                self._source_image = ImageOps.exif_transpose(opened_image).convert(
                    "RGBA"
                )
        except (OSError, ValueError) as error:
            logger.exception("Could not open replacement image %s", image_path)
            QMessageBox.warning(
                self._page, "Image", f"Could not open this image:\n{error}"
            )
            return False

        self._source_path = self._save_image(self._source_image, "source")
        self._crop_preview.set_source(self._source_path, target_size)
        self._crop_preview.setGeometry(self._preview.rect())
        self.stretch_button.setEnabled(True)
        self.crop_button.setEnabled(True)
        self._fit_mode_changed()
        return True

    def refresh_target_size(self) -> None:
        """Reset the crop when a dynamically-sized asset target changes."""
        if self._source_path:
            self._crop_preview.set_source(
                self._source_path, self._current_target_size()
            )
            self._fit_mode_changed()

    def controls_height(self) -> int:
        """Return vertical space reserved beneath the preview."""
        return (
            max(
                self.stretch_button.sizeHint().height(),
                self.crop_button.sizeHint().height(),
            )
            + 6
        )

    def _current_target_size(self) -> tuple[int, int]:
        return self._target_size() if callable(self._target_size) else self._target_size

    def _fit_mode_changed(self) -> None:
        if self._source_image is None:
            return
        crop_enabled = self.crop_button.isChecked()
        self._crop_preview.setVisible(crop_enabled)
        if crop_enabled:
            self._crop_preview.raise_()
        self._render_output()

    def _render_output(self) -> None:
        if self._source_image is None:
            return
        image = self._source_image
        if self.crop_button.isChecked():
            image = image.crop(self._crop_preview.crop_box())
        image = image.resize(self._current_target_size(), Image.Resampling.LANCZOS)
        output_path = self._save_image(image, "asset")
        self._preview.setPixmap(QPixmap(output_path))
        self._image_ready(output_path)

    @staticmethod
    def _save_image(image: Image.Image, prefix: str) -> str:
        output_path = (
            Path(_IMAGE_TEMP_DIR.path()) / f"{prefix}-{next(_IMAGE_SEQUENCE)}.png"
        )
        image.save(output_path, "PNG")
        return str(output_path)
