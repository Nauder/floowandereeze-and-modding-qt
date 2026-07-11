"""
Aspect ratio preserving QLabel widget.

Provides a QLabel that automatically maintains its aspect ratio during resizing.
"""

from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Qt, QSize


class AspectRatioLabel(QtWidgets.QLabel):
    """
    QLabel that maintains a specific aspect ratio during resizing.

    This widget will scale its content while preserving the aspect ratio,
    making it ideal for responsive image displays.
    """

    def __init__(self, parent=None, aspect_ratio: float = 1.0):
        """
        Initialize the aspect ratio label.

        Args:
            parent: Parent widget
            aspect_ratio: Width/height ratio (e.g., 1.0 for square, 0.68 for portrait 256/374)
        """
        super().__init__(parent)
        self._aspect_ratio = aspect_ratio
        self.setScaledContents(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Set size policy to respect heightForWidth
        size_policy = QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Preferred
        )
        size_policy.setHeightForWidth(True)
        self.setSizePolicy(size_policy)

    def set_aspect_ratio(self, width: int, height: int):
        """Set the aspect ratio from width and height values."""
        if height > 0:
            self._aspect_ratio = width / height
            self.updateGeometry()

    def hasHeightForWidth(self) -> bool:
        """Indicate that this widget's height depends on its width."""
        return True

    def heightForWidth(self, width: int) -> int:
        """Calculate the appropriate height for a given width based on aspect ratio."""
        return int(width / self._aspect_ratio) if self._aspect_ratio > 0 else width

    def sizeHint(self) -> QSize:
        """Provide a default size hint."""
        width = 256  # Default width
        height = self.heightForWidth(width)
        return QSize(width, height)

    def minimumSizeHint(self) -> QSize:
        """Provide a minimum size hint."""
        width = 128  # Minimum width
        height = self.heightForWidth(width)
        return QSize(width, height)
