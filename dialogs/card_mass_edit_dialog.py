import re

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


class CardMassEditDialog(QDialog):
    """Collect a regex replacement that will be applied to every card."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mass Edit Card Text")
        self.setModal(True)
        self.resize(500, 280)

        icon = QIcon()
        icon.addFile(
            ":/ui/images/icon.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off
        )
        self.setWindowIcon(icon)

        layout = QVBoxLayout(self)
        warning = QLabel("This replacement will be applied to all cards in the game.")
        warning.setWordWrap(True)
        layout.addWidget(warning)

        regex_group = QGroupBox("Regex find and replace")
        regex_layout = QFormLayout(regex_group)
        self.regex_input = QLineEdit()
        self.regex_input.setPlaceholderText("Regex to find")
        self.regex_input.setToolTip(
            "Python regular expression. For example: "
            "(?:Destiny|Elemental|Evil|Vision)\\s+HERO"
        )
        self.replacement_input = QLineEdit()
        self.replacement_input.setPlaceholderText("Replacement text")
        self.replacement_input.setToolTip(
            "Replacement text. Capture groups such as \\1 are supported."
        )
        self.names_checkbox = QCheckBox("Names")
        self.names_checkbox.setChecked(True)
        self.descriptions_checkbox = QCheckBox("Descriptions")
        self.descriptions_checkbox.setChecked(True)
        fields_layout = QHBoxLayout()
        fields_layout.addWidget(self.names_checkbox)
        fields_layout.addWidget(self.descriptions_checkbox)
        fields_layout.addStretch()

        regex_layout.addRow("Find:", self.regex_input)
        regex_layout.addRow("Replace with:", self.replacement_input)
        regex_layout.addRow("Text fields:", fields_layout)
        layout.addWidget(regex_group)

        buttons = QHBoxLayout()
        cancel_button = QPushButton("Cancel")
        apply_button = QPushButton("Apply to All Cards")
        cancel_button.clicked.connect(self.reject)
        apply_button.clicked.connect(self._accept_replacement)
        buttons.addWidget(cancel_button)
        buttons.addWidget(apply_button)
        layout.addLayout(buttons)

    def get_inputs(self):
        """Return the regex replacement and selected text fields."""
        return (
            self.regex_input.text(),
            self.replacement_input.text(),
            self.names_checkbox.isChecked(),
            self.descriptions_checkbox.isChecked(),
        )

    def _accept_replacement(self):
        """Validate the regex inputs before accepting the mass edit."""
        pattern, _, names, descriptions = self.get_inputs()

        if not pattern:
            self._show_error("Enter a regular expression to find.")
            return
        if not names and not descriptions:
            self._show_error("Select at least one text field to replace.")
            return

        try:
            re.compile(pattern)
        except re.error as error:
            self._show_error(f"Invalid regular expression: {error}")
            return

        self.accept()

    def _show_error(self, message):
        """Show a validation error without closing the dialog."""
        QMessageBox.warning(self, "Mass edit", message)
