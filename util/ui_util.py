"""
UI utility functions for the application.
This module provides functions for UI-related tasks like showing toasts
and managing the application's color palette.
"""

from PySide6.QtGui import QPalette, QColor
from PySide6.QtCore import Qt
from pyqttoast import Toast, ToastPreset


def show_toast(parent, title: str, text: str, preset: ToastPreset):
    """
    Show a toast notification to the user.

    Args:
        parent: The parent widget for the toast
        title: The title text of the toast
        text: The main text content of the toast
        preset: The visual preset to apply to the toast
    """
    toast = Toast(parent)
    toast.setDuration(5000)
    toast.setBorderRadius(3)
    toast.setTitle(title)
    toast.setText(text)
    toast.applyPreset(preset)
    toast.show()


def get_dark_mode_palette(app=None):
    """
    Create and return a dark mode color palette for the application.

    Args:
        app: The QApplication instance to get the base palette from.
             If None, a new QPalette will be created.

    Returns:
        QPalette: A dark mode color palette configured with appropriate colors
                 for various UI elements.
    """
    dark_palette = app.palette()
    dark_palette.setColor(QPalette.Window, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.WindowText, Qt.white)
    dark_palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor(127, 127, 127))
    dark_palette.setColor(QPalette.Base, QColor(42, 42, 42))
    dark_palette.setColor(QPalette.AlternateBase, QColor(66, 66, 66))
    dark_palette.setColor(QPalette.ToolTipBase, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ToolTipText, Qt.white)
    dark_palette.setColor(QPalette.Text, Qt.white)
    dark_palette.setColor(QPalette.Disabled, QPalette.Text, QColor(127, 127, 127))
    dark_palette.setColor(QPalette.Dark, QColor(35, 35, 35))
    dark_palette.setColor(QPalette.Shadow, QColor(20, 20, 20))
    dark_palette.setColor(QPalette.Button, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ButtonText, Qt.white)
    dark_palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(127, 127, 127))
    dark_palette.setColor(QPalette.BrightText, Qt.red)
    dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.Disabled, QPalette.Highlight, QColor(80, 80, 80))
    dark_palette.setColor(QPalette.HighlightedText, Qt.white)
    dark_palette.setColor(
        QPalette.Disabled,
        QPalette.HighlightedText,
        QColor(127, 127, 127),
    )

    return dark_palette
