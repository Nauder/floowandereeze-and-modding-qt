"""Splitter widgets with a visible, responsive drag grip."""

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets


class GripSplitterHandle(QtWidgets.QSplitterHandle):
    """A splitter handle that makes its drag affordance easy to spot."""

    def __init__(
        self, orientation: QtCore.Qt.Orientation, parent: QtWidgets.QSplitter
    ) -> None:
        super().__init__(orientation, parent)
        self._hovered = False
        cursor = (
            QtCore.Qt.CursorShape.SizeVerCursor
            if orientation == QtCore.Qt.Orientation.Vertical
            else QtCore.Qt.CursorShape.SizeHorCursor
        )
        self.setCursor(cursor)

    def enterEvent(self, event: QtCore.QEvent) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event: QtCore.QEvent) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        super().paintEvent(event)

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(
            QtGui.QColor(205, 218, 210, 220)
            if self._hovered
            else QtGui.QColor(166, 181, 172, 150)
        )

        center = self.rect().center()
        if self.orientation() == QtCore.Qt.Orientation.Vertical:
            offsets = ((-2, -3), (2, -3), (-2, 0), (2, 0), (-2, 3), (2, 3))
        else:
            offsets = ((-3, -2), (0, -2), (3, -2), (-3, 2), (0, 2), (3, 2))

        for x_offset, y_offset in offsets:
            painter.drawEllipse(
                QtCore.QPointF(center.x() + x_offset, center.y() + y_offset),
                1.15,
                1.15,
            )
        painter.end()


class GripSplitter(QtWidgets.QSplitter):
    """A splitter with enough space for the visible drag grip."""

    HANDLE_WIDTH = 10

    def __init__(
        self,
        orientation: QtCore.Qt.Orientation,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(orientation, parent)
        self.setHandleWidth(self.HANDLE_WIDTH)

    def createHandle(self) -> QtWidgets.QSplitterHandle:
        return GripSplitterHandle(self.orientation(), self)
