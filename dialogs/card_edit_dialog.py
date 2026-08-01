import logging
import re

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTextEdit,
    QPushButton,
    QHBoxLayout,
)

from database.models import CardModel
from util.python_utils import remove_alt_tags

logger = logging.getLogger(__name__)


class CardEditDialog(QDialog):
    def __init__(self, card: CardModel):
        super().__init__()
        self.setWindowTitle(f"Editing {card.name}")
        self.setModal(True)
        self.resize(500, 520)

        icon = QIcon()
        icon.addFile(
            ":/ui/images/icon.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off
        )
        self.setWindowIcon(icon)

        self.card = card
        self._action = None

        layout = QVBoxLayout()

        # Name input
        self.name_label = QLabel("Name:")
        self.name_input = QLineEdit()
        self.name_input.setText(remove_alt_tags(self.card.modded_name or card.name))
        layout.addWidget(self.name_label)
        layout.addWidget(self.name_input)

        # Description input
        self.desc_label = QLabel("Description:")
        self.desc_input = QTextEdit()
        self.desc_input.setText(self.card.modded_description or card.description)
        layout.addWidget(self.desc_label)
        layout.addWidget(self.desc_input)

        self._add_regex_replacement_section(layout)

        # Buttons
        button_layout = QHBoxLayout()
        restore_layout = QHBoxLayout()
        self.save_button = QPushButton("Replace")
        self.cancel_button = QPushButton("Cancel")
        self.name_button = QPushButton("Restore Name")
        self.desc_button = QPushButton("Restore Description")

        self.save_button.clicked.connect(self._accept_text_replacement)
        self.cancel_button.clicked.connect(self.reject)
        self.name_button.clicked.connect(
            lambda: self.name_input.setText(self.card.name)
        )
        self.desc_button.clicked.connect(
            lambda: self.desc_input.setText(self.card.description)
        )

        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.save_button)
        restore_layout.addWidget(self.name_button)
        restore_layout.addWidget(self.desc_button)
        layout.addLayout(button_layout)
        layout.addLayout(restore_layout)

        self.setLayout(layout)

    def get_inputs(self):
        """Return the direct name and description replacement inputs."""
        return self.name_input.text(), self.desc_input.toPlainText()

    def get_action(self):
        """Return the action selected when the dialog was accepted."""
        return self._action

    def get_regex_inputs(self):
        """Return the configured regex replacement and its target settings."""
        return (
            self.regex_input.text(),
            self.replacement_input.text(),
            self.names_checkbox.isChecked(),
            self.descriptions_checkbox.isChecked(),
        )

    def _add_regex_replacement_section(self, layout):
        """Add controls for applying a regex to the selected card."""
        regex_group = QGroupBox("Regex find and replace this card")
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
        targets_layout = QHBoxLayout()
        targets_layout.addWidget(self.names_checkbox)
        targets_layout.addWidget(self.descriptions_checkbox)
        targets_layout.addStretch()
        self.regex_button = QPushButton("Apply Regex to Card")
        self.regex_button.clicked.connect(self._accept_regex_replacement)

        regex_layout.addRow("Find:", self.regex_input)
        regex_layout.addRow("Replace with:", self.replacement_input)
        regex_layout.addRow("Text fields:", targets_layout)
        regex_layout.addRow(self.regex_button)
        layout.addWidget(regex_group)

    def _accept_text_replacement(self):
        """Accept the dialog as a direct text replacement."""
        self._action = "replace"
        self.accept()

    def _accept_regex_replacement(self):
        """Validate the regex inputs before accepting a regex replacement."""
        pattern, _, names, descriptions = self.get_regex_inputs()

        if not pattern:
            self._show_regex_error("Enter a regular expression to find.")
            return
        if not names and not descriptions:
            self._show_regex_error("Select at least one text field to replace.")
            return

        try:
            re.compile(pattern)
        except re.error as error:
            logger.exception("Invalid regular expression in card edit dialog")
            self._show_regex_error(f"Invalid regular expression: {error}")
            return

        self._action = "regex"
        self.accept()

    def _show_regex_error(self, message):
        """Show a validation error without closing the dialog."""
        QMessageBox.warning(self, "Regex replacement", message)
