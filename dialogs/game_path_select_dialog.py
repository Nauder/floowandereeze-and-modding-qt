"""Dialog for choosing a Master Duel player-data directory."""

from os.path import basename

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)


class GamePathSelectDialog(QDialog):
    """Let the user choose one of the Master Duel paths found in Steam."""

    def __init__(self, game_paths: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Master Duel Player Data")
        self.setModal(True)
        self.setMinimumWidth(720)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                f"Found {len(game_paths)} valid game path"
                f"{'s' if len(game_paths) != 1 else ''}. Select the Master Duel "
                "account to use. Each entry shows its player ID and data directory."
            )
        )

        self.path_list = QListWidget(self)
        self.path_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        for game_path in game_paths:
            item = QListWidgetItem(
                f"Player ID: {basename(game_path)}\n{game_path}", self.path_list
            )
            item.setData(Qt.ItemDataRole.UserRole, game_path)
        layout.addWidget(self.path_list)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.path_list.currentItemChanged.connect(self._update_accept_button)
        layout.addWidget(self.button_box)

    def selected_game_path(self) -> str | None:
        """Return the currently selected player-data path, if any."""
        selected_item = self.path_list.currentItem()
        if selected_item:
            return selected_item.data(Qt.ItemDataRole.UserRole)
        return None

    def _update_accept_button(self, _current=None, _previous=None) -> None:
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(
            self.path_list.currentItem() is not None
        )
