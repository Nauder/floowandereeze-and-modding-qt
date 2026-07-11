"""
Responsive page mixin for dynamic UI scaling.

Provides base functionality for pages to adapt to different window sizes
while maintaining aspect ratios and usability.
"""

from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import QSize, Qt
from typing import Tuple, Optional, Dict


class AspectRatioLabel(QtWidgets.QLabel):
    """QLabel that maintains aspect ratio during resizing."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._aspect_ratio = 1.0
        self.setScaledContents(True)
        size_policy = QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding
        )
        size_policy.setHeightForWidth(True)
        self.setSizePolicy(size_policy)

    def set_aspect_ratio(self, width: float, height: float):
        """Set aspect ratio from width/height values."""
        if height > 0:
            self._aspect_ratio = width / height
            self.updateGeometry()

    def hasHeightForWidth(self) -> bool:
        """Widget height depends on width to maintain aspect ratio."""
        return True

    def heightForWidth(self, width: int) -> int:
        """Calculate height from width to maintain aspect ratio."""
        return int(width / self._aspect_ratio) if self._aspect_ratio > 0 else width


class ResponsivePageMixin:
    """
    Mixin class to add responsive behavior to page widgets.
    Dynamically adjusts image preview sizes and layout based on window size.

    Usage:
        class MyPage(ResponsivePageMixin, QtWidgets.QWidget, Ui_MyPage):
            def __init__(self):
                QtWidgets.QWidget.__init__(self)
                ResponsivePageMixin.__init__(self)
                self.setupUi(self)
                self.setup_responsive_images(
                    self.current_label,
                    self.preview_label,
                    aspect_ratio=(256, 374)
                )
    """

    def __init__(self):
        """Initialize responsive properties"""
        self._original_image_aspect_ratios: Dict[QtWidgets.QLabel, Tuple[int, int]] = {}
        self._min_image_size = 128
        self._max_image_size = 500

    def setup_responsive_images(
        self,
        current_label: Optional[QtWidgets.QLabel],
        preview_label: Optional[QtWidgets.QLabel],
        aspect_ratio: Tuple[int, int] = (1, 1),
        max_image_size: Optional[int] = None,
        min_image_size: Optional[int] = None,
    ):
        """
        Configure labels for responsive image display.

        Args:
            current_label: QLabel showing current image (can be None for pages without it)
            preview_label: QLabel showing preview image (can be None for pages without it)
            aspect_ratio: Tuple of (width, height) ratio
                         Examples: (256, 374) for portrait cards
                                   (374, 374) for square images
                                   (1920, 1080) for landscape backgrounds
            max_image_size: Optional maximum display width for these labels
            min_image_size: Optional minimum display width for these labels
        """
        if max_image_size is not None:
            self._max_image_size = max_image_size
        if min_image_size is not None:
            self._min_image_size = min_image_size

        labels = [label for label in [current_label, preview_label] if label is not None]

        for label in labels:
            self._original_image_aspect_ratios[label] = aspect_ratio

            # Inject aspect ratio behavior by monkey-patching the label
            label._aspect_ratio = aspect_ratio[0] / aspect_ratio[1]

            # Override hasHeightForWidth and heightForWidth
            label.hasHeightForWidth = lambda: True
            label.heightForWidth = lambda w, ar=aspect_ratio[0]/aspect_ratio[1]: int(w / ar)

            # Set size policies for responsive behavior
            label.setScaledContents(True)
            size_policy = QtWidgets.QSizePolicy(
                QtWidgets.QSizePolicy.Policy.Preferred,
                QtWidgets.QSizePolicy.Policy.Preferred
            )
            size_policy.setHeightForWidth(True)
            label.setSizePolicy(size_policy)

    def setup_responsive_coin_images(
        self,
        current_head: Optional[QtWidgets.QLabel],
        current_tail: Optional[QtWidgets.QLabel],
        preview_head: Optional[QtWidgets.QLabel],
        preview_tail: Optional[QtWidgets.QLabel]
    ):
        """
        Special setup for coin page with 4 circular images.
        Coin images are always square (1:1 aspect ratio).

        Args:
            current_head: Current head texture label
            current_tail: Current tail texture label
            preview_head: Preview head texture label
            preview_tail: Preview tail texture label
        """
        labels = [label for label in [current_head, current_tail, preview_head, preview_tail]
                  if label is not None]

        for label in labels:
            # Coin images are always square
            self._original_image_aspect_ratios[label] = (1, 1)

            label.setScaledContents(True)
            size_policy = QtWidgets.QSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Expanding
            )
            size_policy.setHeightForWidth(True)
            label.setSizePolicy(size_policy)

    def resizeEvent(self, event: QtCore.QEvent):
        """Handle window resize to adjust image sizes"""
        super().resizeEvent(event)
        self._adjust_image_sizes()

    def _adjust_image_sizes(self):
        """Dynamically adjust image preview sizes based on available space"""
        if not self._original_image_aspect_ratios:
            return

        # Get available width and height
        available_width = self.width()
        available_height = self.height()

        # Calculate optimal base size with responsive breakpoints
        if available_width < 1024:  # Small screens
            target_base = min(available_width // 3, 256)
        elif available_width < 1366:  # Medium screens
            target_base = min(available_width // 3, 320)
        elif available_width < 1920:  # Large screens
            target_base = min(available_width // 3, 400)
        else:  # Very large screens (4K)
            target_base = min(available_width // 3, 500)

        # Clamp to min/max
        target_base = max(self._min_image_size, min(target_base, self._max_image_size))

        # Apply to labels - heightForWidth will maintain aspect ratio
        for label, (aspect_w, aspect_h) in self._original_image_aspect_ratios.items():
            # Set maximum width only - height will be calculated by heightForWidth
            label.setMaximumWidth(target_base)
            label.setMinimumWidth(self._min_image_size)

            # Remove height constraints - let heightForWidth control it
            label.setMaximumHeight(16777215)  # Qt's QWIDGETSIZE_MAX
            label.setMinimumHeight(0)

            # Force layout to recalculate with heightForWidth
            label.updateGeometry()

    def _adjust_list_view_icons(self, list_view: QtWidgets.QListView, base_width: int, base_height: int):
        """
        Dynamically adjust QListView icon sizes based on window width.
        Call this from resizeEvent if you want responsive thumbnail grids.

        Args:
            list_view: The QListView widget to adjust
            base_width: Base icon width (e.g., 256)
            base_height: Base icon height (e.g., 362)
        """
        if not list_view:
            return

        width = self.width()

        # Calculate icon size based on width (show 3-6 items per row)
        if width < 1024:
            scale = 0.7  # 70% of base size
        elif width < 1920:
            scale = 0.85  # 85% of base size
        else:
            scale = 1.0  # Full size

        icon_width = int(base_width * scale)
        icon_height = int(base_height * scale)

        list_view.setIconSize(QSize(icon_width, icon_height))
