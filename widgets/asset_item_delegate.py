"""Delegates for asset grid presentation."""

from PySide6 import QtCore, QtGui, QtWidgets


class AssetStateBadgeDelegate(QtWidgets.QStyledItemDelegate):
    """Overlay small state badges on asset grid items without changing model data."""

    def paint(self, painter, option, index):
        super().paint(painter, option, index)

        asset = self._asset_for_index(index)
        if not asset:
            return

        badges = self._badges_for_asset(asset)
        if not badges:
            return

        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        x = option.rect.left() + 6
        y = option.rect.top() + 6
        metrics = option.fontMetrics

        for text, color in badges:
            text_width = metrics.horizontalAdvance(text)
            rect = QtCore.QRect(x, y, text_width + 12, metrics.height() + 6)
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(QtGui.QColor(color))
            painter.drawRoundedRect(rect, 3, 3)
            painter.setPen(QtGui.QColor("#ffffff"))
            painter.drawText(rect, QtCore.Qt.AlignmentFlag.AlignCenter, text)
            y += rect.height() + 4

        painter.restore()

    @staticmethod
    def _asset_for_index(index):
        model = index.model()
        if hasattr(model, "assets"):
            return model.assets[index.row()]
        if hasattr(model, "fields"):
            return model.fields[index.row()]
        return None

    @staticmethod
    def _badges_for_asset(asset):
        badges = []
        if getattr(asset, "favorite", False):
            badges.append(("Fav", "#7c5cff"))
        if getattr(asset, "has_backup", False):
            badges.append(("Bkp", "#b36b00"))
        if getattr(asset, "modded_name", None) or getattr(
            asset, "modded_description", None
        ):
            badges.append(("Txt", "#008a5c"))
        return badges
