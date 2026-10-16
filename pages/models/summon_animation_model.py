"""Searchable card identities for detached summon component metadata."""

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt


class SummonAnimationModel(QAbstractListModel):
    """Group by region/card ID; display names are labels only."""

    def __init__(self, rows=(), parent=None):
        super().__init__(parent)
        self.rows = list(rows)
        self.cards = []
        self.filter("")

    def filter(self, text, game_region=None):
        self.beginResetModel()
        cards = {}
        for row in self.rows:
            if row["card_id"] is None or (
                game_region and row["game_region"] != game_region
            ):
                continue
            key = (row["game_region"], row["card_id"])
            cards[key] = row["display_name"] or f"Card {row['card_id']}"
        self.cards = sorted(
            [
                (key, name)
                for key, name in cards.items()
                if text.casefold() in f"{name} {key[1]}".casefold()
            ],
            key=lambda item: (item[1].casefold(), item[0]),
        )
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.cards)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.cards):
            return None
        key, name = self.cards[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return f"{name} ({key[1]})"
        if role == Qt.ItemDataRole.UserRole:
            return key
        return None
