from typing_extensions import Optional
from PySide6 import QtWidgets, QtCore
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFileDialog, QCompleter
from pyqttoast import ToastPreset

from database.models import CardModel
from dialogs.card_edit_dialog import CardEditDialog
from pages.models.card_list_model import CardListModel
from pages.ui.card import Ui_Card
from services.card_service import CardService
from unity.unity_utils import fetch_bundle_thumb
from util.constants import IMAGE_FILTER, APP_CONFIG
from util.python_utils import remove_alt_tags
from util.ui_util import show_toast


class Card(QtWidgets.QWidget, Ui_Card):
    def __init__(self):
        super(Card, self).__init__()
        self.setupUi(self)

        self.service = CardService()
        self.model = CardListModel()
        self.cardsView.setModel(self.model)
        self.selected: Optional[CardModel] = None

        self._connect_callbacks()

    def _connect_callbacks(self):
        self.cardsView.clicked.connect(self._on_card_clicked)
        self.selectButton.clicked.connect(self._select_image)
        self.replaceButton.clicked.connect(self._replace)
        self.copyButton.clicked.connect(self._copy)
        self.extractButton.clicked.connect(self._extract_texture)
        self.searchButton.clicked.connect(self._search)
        self.restoreButton.clicked.connect(self._restore)
        self.editButton.clicked.connect(self._open_edit_modal)
        self.searchEdit.returnPressed.connect(self._search)

        self.searchEdit.setCompleter(QCompleter(self.service.get_names()))
        self.searchEdit.completer().setCaseSensitivity(
            QtCore.Qt.CaseSensitivity.CaseInsensitive
        )
        self.searchEdit.completer().setFilterMode(QtCore.Qt.MatchFlag.MatchContains)
        self.searchEdit.completer().activated.connect(self._search)

    def _open_edit_modal(self):
        dialog = CardEditDialog(self.selected)

        if dialog.exec():
            name, description = dialog.get_inputs()
            if name and description:
                # This is done in a pretty inefficient way, but one missing card and the game can break, so everything
                # needs to be updated before any changes, in case of any CARD_* file update.
                if name != remove_alt_tags(self.selected.name):
                    self.service.replace_name(name)
                if description != self.selected.description:
                    self.service.replace_description(description)
                self.model.refresh()
                show_toast(
                    self,
                    "Text Edit",
                    "Card text edited successfully",
                    ToastPreset.SUCCESS_DARK,
                )

    def _restore(self):
        if self.service.restore_asset():
            self.model.refresh()
            show_toast(
                self, "Backup", "Card restored successfully", ToastPreset.SUCCESS_DARK
            )
        else:
            show_toast(
                self, "Backup", "Card backup not found", ToastPreset.WARNING_DARK
            )

    def _on_card_clicked(self, index):
        self.selected = self.model.assets[index.row()]

        self.current.setPixmap(
            fetch_bundle_thumb(
                self.selected.bundle, (374, 374), self.selected.unity_file
            ).pixmap(374, 374)
        )
        self.service.bundle = self.selected.bundle
        self.service.unity_file = self.selected.unity_file

        modded_name = (
            f"- <i style='color:#ccffcc'>{self.selected.modded_name}</i> "
            if self.selected.modded_name
            else ""
        )
        self.bundle.setText(
            f"Editing {self.model.assets[index.row()].name} {modded_name}({self.selected.bundle})"
        )

        self.replaceButton.setEnabled(True)
        self.extractButton.setEnabled(True)
        self.restoreButton.setEnabled(True)
        self.copyButton.setEnabled(True)
        self.editButton.setEnabled(True)

    def _select_image(self):
        file, _ = QFileDialog.getOpenFileUrl(self, "Select Image", "", IMAGE_FILTER)

        if file and file.url() != "":
            local_file = file.toLocalFile()

            self.cardEdit.setText(local_file)
            self.preview.setPixmap(QPixmap(local_file))
            self.service.image_path = local_file

    def _copy(self):
        if not self.service.unity_file:
            self.service.copy_bundle()
            show_toast(
                self,
                "Card Copying",
                'Card copied to the "cards" folder',
                ToastPreset.SUCCESS_DARK,
            )
        else:
            show_toast(
                self,
                "Card Copying",
                "Cannot copy Unity3D card",
                ToastPreset.WARNING_DARK,
            )

    def _extract_texture(self):
        self.service.extract_texture(self.service.bundle)
        show_toast(
            self,
            "Card Extraction",
            'Card extracted to the "cards" folder',
            ToastPreset.SUCCESS_DARK,
        )

    def _replace(self):
        if APP_CONFIG.create_backup and not self.selected.has_backup:
            self.service.create_backup(self.service.bundle)
            self.model.set_backup_state(self.selected.id, True)

        self.service.replace_bundle()
        self.model.refresh()
        self.current.setPixmap(
            fetch_bundle_thumb(
                self.service.bundle, (374, 374), self.service.unity_file
            ).pixmap(374, 374)
        )

        show_toast(
            self, "Card", "Card replacement successful", ToastPreset.SUCCESS_DARK
        )

    def _search(self):
        search_filter = self.searchEdit.text()

        if len(search_filter) >= 3:
            self.model.filter = search_filter

            self.model.refresh()

            self.model.layoutChanged.emit()
        else:
            show_toast(
                self,
                "Search",
                "Please use 3 or more characters to search",
                ToastPreset.INFORMATION_DARK,
            )
