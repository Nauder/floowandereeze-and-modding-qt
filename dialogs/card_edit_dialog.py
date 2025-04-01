from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QPushButton,
    QHBoxLayout,
)

from database.models import CardModel
from util.python_utils import remove_alt_tags


class CardEditDialog(QDialog):
    def __init__(self, card: CardModel):
        super().__init__()
        self.setWindowTitle(f"Editing {card.name}")
        self.setModal(True)
        self.resize(400, 300)

        icon = QIcon()
        icon.addFile(
            ":/ui/images/icon.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off
        )
        self.setWindowIcon(icon)

        self.card = card

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

        # Buttons
        button_layout = QHBoxLayout()
        restore_layout = QHBoxLayout()
        self.save_button = QPushButton("Replace")
        self.cancel_button = QPushButton("Cancel")
        self.name_button = QPushButton("Restore Name")
        self.desc_button = QPushButton("Restore Description")

        self.save_button.clicked.connect(self.accept)
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
        return self.name_input.text(), self.desc_input.toPlainText()
