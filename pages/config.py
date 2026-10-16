from datetime import datetime
import logging
import os
from threading import Thread

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressDialog,
    QRadioButton,
    QWidget,
)
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from pyqttoast import ToastPreset

from database.objects import session
from database.models import (
    CardModel,
    CardOcgModel,
    SleeveModel,
    SleeveOcgModel,
    IconModel,
    CardIconModel,
    CoinModel,
    DeckBoxModel,
    SummonAnimationAssetModel,
)
from dialogs.game_path_select_dialog import GamePathSelectDialog
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
    update_summon_animations,
)
from util.constants import APP_CONFIG, IMAGE_FILTER
from util.metadata_source import (
    DEFAULT_METADATA_REPOSITORY,
    DEFAULT_METADATA_BRANCH,
    normalize_metadata_source,
    metadata_source_key,
)
from util.python_utils import (
    find_steam_master_duel_paths,
    get_instances_of_subclasses,
    is_valid_game_path,
)
from util.ui_util import show_toast
from widgets.ux import set_button_roles

logger = logging.getLogger(__name__)


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
        self.autoDetectGameButton.clicked.connect(self._auto_detect_game_path)
        self.updateButton.clicked.connect(self._check_update)
        self.saveMetadataSourceButton.clicked.connect(
            lambda: self._save_metadata_source()
        )
        self.resetMetadataSourceButton.clicked.connect(self._reset_metadata_source)
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

        for radio in [self.tcg_region_button, self.ocg_region_button]:
            radio.toggled.connect(lambda checked, r=radio: self._set_asset_region(r))

    def _configure_ux(self):
        """Add section labels and shared button hierarchy to the config page."""
        self.bgLine.setPlaceholderText("Select or drop an image")
        self.gameLine.setPlaceholderText("Select Master Duel 0x000000 folder")
        self.updateLine.setPlaceholderText("No data version installed")

        sections = [
            (0, "Game Data"),
            (4, "Appearance"),
            (9, "Card Text"),
            (12, "Backups"),
            (15, "Asset Build Settings"),
            (19, "Metadata Source"),
        ]
        for index, title in sections:
            self._insert_config_section(index, title)

        region_label = QLabel("Game Version:", self)
        region_label.setToolTip("Select the card and sleeve data for your game version")
        self.maincontent.addWidget(region_label, 2, 0)

        region_widget = QWidget(self)
        region_layout = QHBoxLayout(region_widget)
        region_layout.setContentsMargins(0, 0, 0, 0)
        region_layout.setSpacing(12)
        self.tcg_region_button = QRadioButton("TCG", region_widget)
        self.tcg_region_button.setObjectName("tcgRegionButton")
        self.ocg_region_button = QRadioButton("OCG", region_widget)
        self.ocg_region_button.setObjectName("ocgRegionButton")
        region_layout.addWidget(self.tcg_region_button)
        region_layout.addWidget(self.ocg_region_button)
        region_layout.addStretch(1)
        self.maincontent.addWidget(region_widget, 2, 1)
        self.maincontent.setColumnStretch(1, 1)

        set_button_roles(self)

    def _insert_config_section(self, index: int, title: str) -> None:
        if index:
            separator = QFrame(self.configPanel)
            separator.setObjectName(f"{title.replace(' ', '').lower()}Separator")
            separator.setFixedHeight(1)
            separator.setStyleSheet("background-color: rgba(255, 255, 255, 0.18);")
            self.maincontent.addWidget(separator, index - 1, 0, 1, 2)
            self.maincontent.setRowMinimumHeight(index - 1, 9)

        label = QLabel(title, self.configPanel)
        label.setObjectName(f"{title.replace(' ', '').lower()}SectionLabel")
        label.setStyleSheet("font-weight: 600; color: #ffffff; margin-top: 4px;")
        self.maincontent.addWidget(label, index, 0, 1, 2)

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

    def _set_asset_region(self, radio):
        """Persist the selected card/sleeve game version for the next launch."""
        if not radio.isChecked():
            return

        region = "ocg" if radio is self.ocg_region_button else "tcg"
        if region == APP_CONFIG.asset_region:
            return

        APP_CONFIG.asset_region = region
        session.commit()
        show_toast(
            self,
            "Game Version",
            "Game version set, restart the app to see changes",
            ToastPreset.SUCCESS_DARK,
        )

    def _set_mip_count(self):
        APP_CONFIG.mip_count = self.mipBox.value()

    def _apply_background_style(self, file_path):
        """Apply background image with the selected mode (stretched or cropped)."""
        self.window().set_background(file_path, APP_CONFIG.background_mode)

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
            self._set_game_path(folder)

    def _auto_detect_game_path(self):
        game_paths = find_steam_master_duel_paths()
        if not game_paths:
            show_toast(
                self,
                "Game Path",
                "Could not find Master Duel player data in your Steam libraries",
                ToastPreset.WARNING_DARK,
            )
            return

        dialog = GamePathSelectDialog(game_paths, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected_game_path = dialog.selected_game_path()
            if selected_game_path:
                self._set_game_path(selected_game_path)

    def _set_game_path(self, folder: str):
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
        self.metadataRepositoryLine.setText(
            APP_CONFIG.metadata_repository or DEFAULT_METADATA_REPOSITORY
        )
        self.metadataBranchLine.setText(
            APP_CONFIG.metadata_branch or DEFAULT_METADATA_BRANCH
        )
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

        selected_region = (APP_CONFIG.asset_region or "tcg").lower()
        self.ocg_region_button.setChecked(selected_region == "ocg")
        self.tcg_region_button.setChecked(selected_region != "ocg")

    def _save_metadata_source(self, notify=True):
        """Persist a validated source; do not invalidate edits or downloaded data."""
        try:
            repository, branch = normalize_metadata_source(
                self.metadataRepositoryLine.text(), self.metadataBranchLine.text()
            )
        except ValueError as error:
            show_toast(self, "Metadata Source", str(error), ToastPreset.WARNING_DARK)
            return False
        APP_CONFIG.metadata_repository = repository
        APP_CONFIG.metadata_branch = branch
        session.commit()
        self.metadataRepositoryLine.setText(repository)
        self.metadataBranchLine.setText(branch)
        if notify:
            show_toast(
                self,
                "Metadata Source",
                "Source saved. Choose Check to refresh metadata.",
                ToastPreset.SUCCESS_DARK,
            )
        return True

    def _reset_metadata_source(self):
        """Restore the original repository and its default-branch behavior."""
        self.metadataRepositoryLine.setText(DEFAULT_METADATA_REPOSITORY)
        self.metadataBranchLine.setText(DEFAULT_METADATA_BRANCH)
        self._save_metadata_source()

    def _check_update(self):
        if not self._save_metadata_source(notify=False):
            return
        if APP_CONFIG.game_path is not None:
            try:
                self._get_data()
            except (OSError, ValueError, RuntimeError) as error:
                show_toast(self, "Update", str(error), ToastPreset.ERROR_DARK)
        else:
            show_toast(
                self,
                "Update",
                "Game Path must be set to update app",
                ToastPreset.WARNING_DARK,
            )

    def _get_data(self):
        source = metadata_source_key(
            APP_CONFIG.metadata_repository, APP_CONFIG.metadata_branch
        )
        remote = get_github_raw_file("data/version.txt")
        local = APP_CONFIG.version
        ocg_data_missing = (
            session.query(CardOcgModel.id).first() is None
            or session.query(SleeveOcgModel.id).first() is None
        )

        names_missing = any(
            session.query(model.id).filter(model.display_name.is_not(None)).first()
            is None
            for model in (
                SleeveModel,
                IconModel,
                CardIconModel,
                CoinModel,
                DeckBoxModel,
            )
        )

        if (
            not local
            or APP_CONFIG.metadata_last_source != source
            or session.query(SummonAnimationAssetModel.id).first() is None
            or names_missing
            or ocg_data_missing
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
                ("summon animations", update_summon_animations),
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

            errors = []

            def run_update(task):
                try:
                    task()
                except Exception as error:
                    logger.exception("Metadata update failed")
                    errors.append(str(error))

            for task_index, (task_name, update_task) in enumerate(
                update_tasks, start=1
            ):
                progress.setLabelText(
                    f"Updating {task_name} ({task_index}/{len(update_tasks)})"
                )
                thread = Thread(target=run_update, args=(update_task,))
                thread.start()
                thread.join()
                progress.setValue(task_index)

            progress.close()

            if errors:
                session.rollback()
                show_toast(
                    self,
                    "Update",
                    f"Data update failed: {errors[0]}",
                    ToastPreset.ERROR_DARK,
                )
                return

            APP_CONFIG.version = remote
            APP_CONFIG.metadata_last_source = source
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

        self.window().set_background(None, "stretched")

    def _apply_all_text_edits(self) -> None:
        """Applies all text edits saved in the database to the game files."""

        # Get all cards with text edits
        card_model = CardOcgModel if APP_CONFIG.asset_region == "ocg" else CardModel
        modified_cards = (
            session.query(card_model)
            .filter(
                (card_model.modded_name.isnot(None))
                | (card_model.modded_description.isnot(None))
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
        card_model = CardOcgModel if APP_CONFIG.asset_region == "ocg" else CardModel
        modified_cards = (
            session.query(card_model)
            .filter(
                (card_model.modded_name.isnot(None))
                | (card_model.modded_description.isnot(None))
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
            logger.exception("Text edits could not be restored")
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
