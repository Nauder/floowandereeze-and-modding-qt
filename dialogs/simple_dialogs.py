from PySide6.QtWidgets import QColorDialog, QMessageBox


def show_color_dialog():
    color = QColorDialog.getColor()

    if color.isValid():
        return color

    return None


def show_confirmation_dialog(message: str, warning=False) -> bool:
    message_box = QMessageBox()
    message_box.setIcon(
        QMessageBox.Warning if warning else QMessageBox.Question
    )  # Set the icon to "Question"
    message_box.setWindowTitle("Confirmation")
    message_box.setText(message)
    message_box.setStandardButtons(
        QMessageBox.Yes | QMessageBox.No
    )  # Add Yes and No buttons
    message_box.setDefaultButton(QMessageBox.No)  # Set default focus to "No"

    return message_box.exec() == QMessageBox.Yes
