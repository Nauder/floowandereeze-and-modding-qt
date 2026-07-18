from datetime import datetime
import os
from threading import Thread

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QLabel, QWidget, QProgressDialog
from PySide6.QtGui import QDragEnterEvent, QDropEvent
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
    update_card_icons,
    update_faces,
    update_wallpapers,
    update_fields,
    update_icons,
    update_boxes,
    get_github_raw_file,
    update_card_metadata,
    update_coins,
)
from util.constants import APP_CONFIG, IMAGE_FILTER, BG_TEMPLATE
from util.python_utils import get_instances_of_subclasses, is_valid_game_path
from util.ui_util import show_toast
from widgets.ux import set_button_roles


class Config(QWidget, Ui_Config):
    """
    Main configuration page.

    This page contains the configuration for the app, including the game path,
    background image, and backup settings.
    """

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self._configure_ux()
        self._connect_callbacks()
        self._set_variables()
        # Enable drag and drop
        self.setAcceptDrops(True)

    # Wrong naming convention for Python, but it's what Qt uses
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Accepts drag and drop of image files."""

        if event.mimeData().hasUrls():
            # Check if the dragged file is an image
            for url in event.mimeData().urls():
                if (
                    url.toLocalFile()
                    .lower()
                    .endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif"))
                ):
                    event.acceptProposedAction()
                    return
        event.ignore()

    # Wrong naming convention for Python, but it's what Qt uses
    def dropEvent(self, event: QDropEvent) -> None:
        """Handles the drop event of an image file."""

        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif")):
                APP_CONFIG.background_path = file_path
                session.commit()
                self.bgLine.setText(APP_CONFIG.background_path)

                self._apply_background_style(file_path)
                show_toast(
                    self,
                    "Background",
                    "Background image set successfully",
                    ToastPreset.SUCCESS_DARK,
                )
                break

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
        # This returns the matching service per model while the naming standard holds.
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

        # Connect background mode radio buttons
        for radio in [self.stretchedButton, self.croppedButton]:
            radio.toggled.connect(lambda checked, r=radio: self._set_background_mode(r))

    def _configure_ux(self):
        """Add section labels and shared button hierarchy to the config page."""
        self.bgLine.setPlaceholderText("Select or drop an image")
        self.gameLine.setPlaceholderText("Select Master Duel 0x000000 folder")
        self.updateLine.setPlaceholderText("No data version installed")

        sections = [
            (6, "Asset Build Settings"),
            (5, "Backups"),
            (4, "Card Text"),
            (1, "Appearance"),
            (0, "Game Data"),
        ]
        for index, title in sections:
            self._insert_config_section(index, title)

        set_button_roles(self)

    def _insert_config_section(self, index: int, title: str) -> None:
        label = QLabel(title, self)
        label.setObjectName(f"{title.replace(' ', '').lower()}SectionLabel")
        label.setStyleSheet("font-weight: 600; color: #ffffff; margin-top: 10px;")
        self.verticalLayout_5.insertWidget(index, label)

        spacer = QLabel("", self)
        spacer.setObjectName(f"{title.replace(' ', '').lower()}SectionSpacer")
        spacer.setStyleSheet("margin-top: 10px;")
        self.verticalLayout_3.insertWidget(index, spacer)

    def _set_packer(self, radio):
        # Ignore the event if it was turned off
        if radio.isChecked():
            packer = radio.objectName().replace("Button", "")
            if packer != APP_CONFIG.packer:
                APP_CONFIG.packer = packer

    def _set_background_mode(self, radio):
        # Ignore the event if it was turned off
        if radio.isChecked() and APP_CONFIG.game_path:
            mode = radio.objectName().replace("Button", "")
            if mode != APP_CONFIG.background_mode:
                APP_CONFIG.background_mode = mode
                session.commit()
                # Reapply background with new mode if background is set
                if APP_CONFIG.background_path:
                    self._apply_background_style(APP_CONFIG.background_path)

    def _set_mip_count(self):
        APP_CONFIG.mip_count = self.mipBox.value()

    def _apply_background_style(self, file_path):
        """Apply background image with the selected mode (stretched or cropped)."""
        background_mode = APP_CONFIG.background_mode

        if background_mode == "cropped":
            # Use background-size: cover to scale image to smallest size that covers whole window
            bg_style = f"border-image: url('{file_path}') 0 0 0 0 repeat repeat;"
        else:  # stretched (default)
            bg_style = f"border-image: url('{file_path}');"

        self.parent().parent().parent().setStyleSheet(
            BG_TEMPLATE.replace("$BG$", bg_style)
        )

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

        # Set background mode radio buttons
        background_mode = APP_CONFIG.background_mode or "stretched"
        for radio in [self.stretchedButton, self.croppedButton]:
            if radio.objectName().startswith(background_mode):
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
            update_tasks = [
                ("sleeves", update_sleeves),
                ("cards", update_cards),
                ("card icons", update_card_icons),
                ("faces", update_faces),
                ("wallpapers", update_wallpapers),
                ("fields", update_fields),
                ("icons", update_icons),
                ("deck boxes", update_boxes),
                ("card metadata", update_card_metadata),
                ("coins", update_coins),
            ]

            # Create progress dialog
            progress = QProgressDialog(
                "Preparing data update...", "Cancel", 0, len(update_tasks), self
            )
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.setWindowTitle("Updating")
            progress.setCancelButton(
                None
            )  # Remove cancel button since we can't cancel the update
            progress.show()

            for task_index, (task_name, update_task) in enumerate(
                update_tasks, start=1
            ):
                progress.setLabelText(
                    f"Updating {task_name} ({task_index}/{len(update_tasks)})"
                )
                thread = Thread(target=update_task)
                thread.start()
                thread.join()
                progress.setValue(task_index)

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

            self._apply_background_style(file.toLocalFile())

    def _reset_background(self):
        APP_CONFIG.background_path = None
        session.commit()
        self.bgLine.setText("")

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

        if not show_confirmation_dialog(
            f"Reapply text edits to {len(modified_cards)} cards?", True
        ):
            return

        # Create progress dialog
        progress = QProgressDialog(
            f"Applying text edits to {len(modified_cards)} cards...",
            "Cancel",
            0,
            len(modified_cards),
            self,
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
            progress.setLabelText(
                f"Applying text edits ({success_count + 1}/{len(modified_cards)})"
            )
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

        if not show_confirmation_dialog(
            f"Restore original text for {len(modified_cards)} cards?", True
        ):
            return

        card_service = CardService()
        try:
            success_count = card_service.restore_text_edits(modified_cards)
        except (OSError, RuntimeError, ValueError) as error:
            show_toast(
                self,
                "Text Edits",
                f"Text edits could not be restored: {error}",
                ToastPreset.ERROR_DARK,
            )
            return

        show_toast(
            self,
            "Text Edits",
            f"Successfully restored {success_count} text edits",
            ToastPreset.SUCCESS_DARK,
        )
