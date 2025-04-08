from datetime import datetime
import os
from threading import Thread

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QWidget, QProgressDialog
from pyqttoast import ToastPreset

from database.objects import session
from database.models import CardModel
from dialogs.simple_dialogs import show_confirmation_dialog
from pages.models.asset_list_model import AssetListModel
from pages.ui.config import Ui_Config
from services.card_service import CardService
from services.unity_service import UnityService
from services.update_service import (
    update_sleeves,
    update_cards,
    update_faces,
    update_wallpapers,
    update_fields,
    update_icons,
    update_boxes,
    get_github_raw_file,
    update_card_metadata,
)
from util.constants import APP_CONFIG, IMAGE_FILTER, BG_TEMPLATE
from util.python_utils import get_instances_of_subclasses, is_valid_game_path
from util.ui_util import show_toast


class Config(QWidget, Ui_Config):
    def __init__(self):
        super(Config, self).__init__()
        self.setupUi(self)
        self._connect_callbacks()
        self._set_variables()

    def restore_all_asset_changes(self) -> None:
        count = 0

        for service, model in self._get_services_and_models():
            backups_path = os.path.join("backups", service.subfolder)

            if os.path.exists(backups_path):
                for filename in os.listdir(backups_path):
                    file_path = os.path.join(backups_path, filename)

                    if os.path.isfile(file_path):
                        service.bundle = filename.replace(".png", "")
                        count += 1 if service.restore_asset() else 0

            model.refresh()

        show_toast(
            self,
            "Backups",
            f"{count} assets have been restored successfully",
            ToastPreset.SUCCESS_DARK,
        )

    def delete_backups(self) -> None:
        count = 0

        for service, model in self._get_services_and_models():
            backups_path = os.path.join("backups", service.subfolder)

            if os.path.exists(backups_path):
                for filename in os.listdir(backups_path):
                    os.remove(os.path.join(backups_path, filename))
                    count += 1

            model.reset_backups()

        show_toast(
            self,
            "Backups",
            f"{count} backups have been deleted successfully",
            ToastPreset.SUCCESS_DARK,
        )

    def _get_services_and_models(self):
        # This SHOULD return the correct service per model as long as the naming standard is followed
        services: list[UnityService] = get_instances_of_subclasses(UnityService)
        models: list[AssetListModel] = get_instances_of_subclasses(AssetListModel)

        return zip(services, models)

    def _connect_callbacks(self):
        self.gameButton.clicked.connect(self._get_game_path)
        self.updateButton.clicked.connect(self._check_update)
        self.bgButton.clicked.connect(self._get_background)
        self.bgResetButton.clicked.connect(self._reset_background)
        self.backupBox.clicked.connect(self._set_use_backups)
        self.restoreButton.clicked.connect(self._restore)
        self.clearButton.clicked.connect(self._delete_backups)
        self.applyTextButton.clicked.connect(self._apply_all_text_edits)
        self.restoreTextButton.clicked.connect(self._restore_all_text_edits)
        self.mipBox.textChanged.connect(self._set_mip_count)
        for radio in [
            self.noneButton,
            self.lzmaButton,
            self.lz4Button,
            self.lz4hcButton,
            self.lzhamButton,
        ]:
            radio.toggled.connect(lambda checked, r=radio: self._set_packer(r))

    def _set_packer(self, radio):
        # Ignore the event if it was turned off
        if radio.isChecked():
            packer = radio.objectName().replace("Button", "")
            if packer != APP_CONFIG.packer:
                APP_CONFIG.packer = packer

    def _set_mip_count(self):
        APP_CONFIG.mip_count = self.mipBox.value()

    def _delete_backups(self):
        if show_confirmation_dialog(
            "Are you sure you want to delete all backups? This action cannot be undone.",
            True,
        ):
            self.delete_backups()

    def _restore(self):
        if show_confirmation_dialog(
            "Are you sure you want to restore all changes? This action cannot be undone.",
            True,
        ):
            self.restore_all_asset_changes()

    def _set_use_backups(self):
        create_backup = self.backupBox.checkState() == Qt.CheckState.Checked
        APP_CONFIG.create_backup = create_backup
        session.commit()

        show_toast(
            self,
            "Backups",
            f'Backups {"enabled" if create_backup else "disabled"}.',
            ToastPreset.SUCCESS_DARK,
        )

    def _get_game_path(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Game Folder")
        if folder and folder != "":
            is_valid = is_valid_game_path(folder)
            if is_valid[0]:
                APP_CONFIG.game_path = folder
                session.commit()
                self.gameLine.setText(APP_CONFIG.game_path)

                if not APP_CONFIG.version:
                    self._check_update()

                show_toast(
                    self,
                    "Game Path",
                    "Game Path set, restart the app to see changes",
                    ToastPreset.SUCCESS_DARK,
                )
            else:
                show_toast(
                    self,
                    "Game Path",
                    f"There was a problem with the Game Path: {is_valid[1]}",
                    ToastPreset.WARNING_DARK,
                )

    def _set_variables(self):
        self.gameLine.setText(APP_CONFIG.game_path)
        self.bgLine.setText(APP_CONFIG.background_path)
        self.updateLine.setText(APP_CONFIG.version)
        self.backupBox.setChecked(APP_CONFIG.create_backup or False)
        self.mipBox.setValue(APP_CONFIG.mipmap_count or 10)
        for radio in [
            self.noneButton,
            self.lzmaButton,
            self.lz4Button,
            self.lz4hcButton,
            self.lzhamButton,
        ]:
            if radio.objectName().startswith(APP_CONFIG.packer or "lz4"):
                radio.setChecked(True)
                break

    def _check_update(self):
        if APP_CONFIG.game_path is not None:
            self._get_data()
        else:
            show_toast(
                self,
                "Update",
                "Game Path must be set to update app",
                ToastPreset.WARNING_DARK,
            )

    def _get_data(self):
        remote = get_github_raw_file("data/version.txt")
        local = APP_CONFIG.version

        if (
            not local
            or datetime.strptime(local.strip(), "%Y-%m-%d").date()
            < datetime.strptime(remote.strip(), "%Y-%m-%d").date()
        ):
            # Create progress dialog
            progress = QProgressDialog("Updating data...", "Cancel", 0, 8, self)
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.setWindowTitle("Updating")
            progress.setCancelButton(
                None
            )  # Remove cancel button since we can't cancel the update
            progress.show()

            update_threads = [
                Thread(target=update_sleeves),
                Thread(target=update_cards),
                Thread(target=update_faces),
                Thread(target=update_wallpapers),
                Thread(target=update_fields),
                Thread(target=update_icons),
                Thread(target=update_boxes),
                Thread(target=update_card_metadata),
            ]

            for thread in update_threads:
                thread.start()
                progress.setValue(progress.value() + 1)

            for thread in update_threads:
                thread.join()

            progress.close()

            APP_CONFIG.version = remote
            session.commit()

            self.updateLine.setText(APP_CONFIG.version)

            show_toast(
                self, "Update", "Data updated successfully", ToastPreset.SUCCESS_DARK
            )
        else:
            show_toast(
                self, "Update", "Data already up to date", ToastPreset.SUCCESS_DARK
            )

    def _get_background(self):
        file, _ = QFileDialog.getOpenFileUrl(self, "Select Image", "", IMAGE_FILTER)

        if file and file.url() != "":
            APP_CONFIG.background_path = file.toLocalFile()
            session.commit()
            self.bgLine.setText(APP_CONFIG.background_path)

            self.parent().parent().parent().setStyleSheet(
                BG_TEMPLATE.replace(
                    "$BG$", f"border-image: url('{file.toLocalFile()}');"
                )
            )

    def _reset_background(self):
        APP_CONFIG.background_path = None
        session.commit()

        self.parent().parent().parent().setStyleSheet(
            BG_TEMPLATE.replace("$BG$", "border-image: url(:/ui/images/bg.png);")
        )

    def _apply_all_text_edits(self) -> None:
        """Applies all text edits saved in the database to the game files."""

        # Get all cards with text edits
        modified_cards = (
            session.query(CardModel)
            .filter(
                (CardModel.modded_name.isnot(None))
                | (CardModel.modded_description.isnot(None))
            )
            .all()
        )

        if not modified_cards:
            show_toast(
                self,
                "Text Edits",
                "No text edits to apply",
                ToastPreset.SUCCESS_DARK,
            )
            return

        # Create progress dialog
        progress = QProgressDialog(
            "Applying text edits...", "Cancel", 0, len(modified_cards), self
        )
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setWindowTitle("Applying Text Edits")
        progress.setCancelButton(
            None
        )  # Remove cancel button since we can't cancel the process
        progress.show()

        card_service = CardService()
        success_count = 0

        for card in modified_cards:
            card_service.bundle = card.bundle
            if card.modded_name:
                card_service.replace_name(card.modded_name)
            if card.modded_description:
                card_service.replace_description(card.modded_description)
            success_count += 1
            progress.setValue(progress.value() + 1)

        progress.close()

        show_toast(
            self,
            "Text Edits",
            f"Successfully applied {success_count} text edits",
            ToastPreset.SUCCESS_DARK,
        )

    def _restore_all_text_edits(self) -> None:
        """Reverts all text edits saved in the database to their original values."""

        # Get all cards with text edits
        modified_cards = (
            session.query(CardModel)
            .filter(
                (CardModel.modded_name.isnot(None))
                | (CardModel.modded_description.isnot(None))
            )
            .all()
        )

        if not modified_cards:
            show_toast(
                self,
                "Text Edits",
                "No text edits to restore",
                ToastPreset.SUCCESS_DARK,
            )
            return

        # Create progress dialog
        progress = QProgressDialog(
            "Restoring text edits...", "Cancel", 0, len(modified_cards), self
        )
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setWindowTitle("Restoring Text Edits")
        progress.setCancelButton(
            None
        )  # Remove cancel button since we can't cancel the process
        progress.show()

        card_service = CardService()
        success_count = 0

        for card in modified_cards:
            card_service.bundle = card.bundle
            if card.modded_name:
                card_service.replace_name(card.name)  # Restore original name
            if card.modded_description:
                card_service.replace_description(
                    card.description
                )  # Restore original description
            success_count += 1
            progress.setValue(progress.value() + 1)

        # Clear all modded fields in the database
        for card in modified_cards:
            card.modded_name = None
            card.modded_description = None
        session.commit()

        progress.close()

        show_toast(
            self,
            "Text Edits",
            f"Successfully restored {success_count} text edits",
            ToastPreset.SUCCESS_DARK,
        )
