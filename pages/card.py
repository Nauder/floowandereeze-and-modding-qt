import logging
import re
from typing import Optional
from PySide6.QtCore import Qt, QSize, QSettings, QTimer
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QCompleter,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QListView,
    QLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from pyqttoast import ToastPreset

from database.models import CardModel
from widgets.grip_splitter import GripSplitter
from database.objects import session
from dialogs.card_edit_dialog import CardEditDialog
from dialogs.card_mass_edit_dialog import CardMassEditDialog
from dialogs.simple_dialogs import show_confirmation_dialog
from pages.base_responsive_page import ResponsivePageMixin
from pages.models.card_list_model import CardListModel
from pages.ui.card import Ui_Card
from services.card_service import CardService
from unity.unity_utils import fetch_bundle_thumb
from util.constants import IMAGE_FILTER, APP_CONFIG
from util.python_utils import remove_alt_tags
from util.ui_util import show_toast
from widgets.ux import configure_editor_chrome, hide_selection_helper, set_button_roles
from widgets.image_fit import InlineImageFitController

logger = logging.getLogger(__name__)


class Card(ResponsivePageMixin, QWidget, Ui_Card):
    RESULT_ITEM_SIZE = QSize(136, 132)
    RESULT_ICON_SIZE = QSize(112, 112)
    RESULTS_MIN_HEIGHT = 315

    def __init__(self):
        QWidget.__init__(self)
        ResponsivePageMixin.__init__(self)
        self.setupUi(self)

        # Configure responsive images with aspect ratio
        self.setup_responsive_images(
            self.current,
            self.preview,
            aspect_ratio=(374, 374),
            max_image_size=500,
        )

        self.service = CardService()
        self._art_id = None
        self._target_art_size = (512, 512)
        self._current_art_size = (512, 512)
        self.model = CardListModel()
        self.cardsView.setModel(self.model)
        self.selected: Optional[CardModel] = None
        self.resultsLabel = None
        self._visible_result_rows = 1
        self.searchHelperLabel = QLabel("", self)
        self.searchHelperLabel.setObjectName("searchHelperLabel")
        self.searchHelperLabel.setStyleSheet("color: #d6d6d6; font-size: 11px;")
        self._settings = QSettings("Floowandereeze", "FloowandereezeAndModding")
        configure_editor_chrome(
            self,
            current_widget=self.current,
            preview_widget=self.preview,
            file_edits=(self.cardEdit,),
            list_views=(self.cardsView,),
            helper_after=self.bundle,
        )
        self.image_fit = InlineImageFitController(
            self,
            self.preview,
            lambda: self._target_art_size,
            lambda image_path: setattr(self.service, "image_path", image_path),
            alignment_widget=self.current,
        )
        set_button_roles(self)
        self._configure_split_layout()
        self.searchEdit.setPlaceholderText("Search cards, min 3 characters")
        self._set_editor_context("Select a Card")
        self._configure_results_grid()
        self._queue_initial_layout_update()

        # Enable drag and drop
        self.setAcceptDrops(True)

        # Initialize the model's search_description property
        self.model.search_description = False

        self._connect_callbacks()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_results_grid()

    def showEvent(self, event):
        super().showEvent(event)
        self._queue_initial_layout_update()

    def _configure_split_layout(self):
        self.verticalLayout.setSpacing(8)
        self.verticalLayout.setContentsMargins(12, 8, 12, 12)
        self.label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.label.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.bundle.hide()

        for layout in (
            self.main_content,
            self.horizontalLayout_3,
            self.horizontalLayout_4,
            self.horizontalLayout,
        ):
            self.verticalLayout.removeItem(layout)
        self.verticalLayout.removeWidget(self.cardsView)

        self._configure_editor_controls()
        for spacer in (
            self.horizontalSpacer_5,
            self.horizontalSpacer_6,
            self.horizontalSpacer_7,
            self.horizontalSpacer_8,
        ):
            self.main_content.removeItem(spacer)
        self.main_content.setSpacing(16)
        self.main_content.setStretch(0, 1)
        self.main_content.setStretch(1, 0)
        self.main_content.setStretch(2, 1)
        current_layout = self.main_content.itemAt(0).layout()
        current_layout.setAlignment(
            self.current, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
        )

        self.editorPanel = QWidget(self)
        self.editorPanel.setObjectName("cardEditorPanel")
        self.editorPanel.setMinimumHeight(230)
        editor_layout = QVBoxLayout(self.editorPanel)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(8)
        editor_layout.addLayout(self.main_content)

        self.resultsPanel = QWidget(self)
        self.resultsPanel.setObjectName("cardResultsPanel")
        self.resultsPanel.setMinimumHeight(self.RESULTS_MIN_HEIGHT)
        results_layout = QVBoxLayout(self.resultsPanel)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.setSpacing(6)
        results_layout.addLayout(self._build_results_header())
        results_layout.addWidget(self.searchHelperLabel)
        results_layout.addWidget(self.cardsView, 1)

        self.cardSplitter = GripSplitter(Qt.Orientation.Vertical, self)
        self.cardSplitter.setObjectName("cardSplitter")
        self.cardSplitter.setChildrenCollapsible(False)
        self.cardSplitter.setOpaqueResize(True)
        self.cardSplitter.addWidget(self.editorPanel)
        self.cardSplitter.addWidget(self.resultsPanel)
        self.cardSplitter.setStretchFactor(0, 3)
        self.cardSplitter.setStretchFactor(1, 2)
        self.cardSplitter.splitterMoved.connect(self._persist_splitter_state)
        self.cardSplitter.splitterMoved.connect(lambda *_: self._queue_layout_update())

        stored_state = self._settings.value("cards/splitter_state")
        if stored_state:
            self.cardSplitter.restoreState(stored_state)
        else:
            self.cardSplitter.setSizes([520, 360])

        self.verticalLayout.addWidget(self.cardSplitter, 1)

    def _configure_editor_controls(self):
        self.label_4.setText("Image source")
        self.label_4.setStyleSheet("font-weight: 600; color: #ffffff;")
        self.cardEdit.setMinimumWidth(210)
        self.cardEdit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

        for layout, widget in (
            (self.verticalLayout_2, self.label_4),
            (self.verticalLayout_3, self.cardEdit),
            (self.verticalLayout_4, self.selectButton),
            (self.horizontalLayout_4, self.restoreButton),
            (self.horizontalLayout_4, self.extractButton),
            (self.horizontalLayout_4, self.copyButton),
            (self.horizontalLayout_4, self.editButton),
            (self.horizontalLayout_4, self.massEditButton),
            (self.horizontalLayout_4, self.replaceButton),
            (self.horizontalLayout_4, self.favorite),
        ):
            layout.removeWidget(widget)

        self.verticalLayout_5.setSpacing(8)
        self.verticalLayout_5.setContentsMargins(0, 26, 0, 0)
        self.verticalLayout_5.addStretch(1)
        self.verticalLayout_5.addWidget(self.label_4)
        self.verticalLayout_5.addWidget(self.cardEdit)
        self.verticalLayout_5.addWidget(self.selectButton)
        self.full_art_check = QCheckBox("Overframe", self)
        self.full_art_check.setObjectName("fullArtCheck")
        self.full_art_check.setEnabled(False)
        self.full_art_check.setToolTip(
            "Check to use overframe framing. Uncheck to use normal framing."
        )
        self.verticalLayout_5.addWidget(self.full_art_check)
        self.art_size_label = QLabel("", self)
        self.art_size_label.setWordWrap(True)
        self.verticalLayout_5.addWidget(self.art_size_label)
        self.locate_full_art_button = QPushButton("Locate overframe data", self)
        self.locate_full_art_button.setObjectName("locateFullArtButton")
        self.locate_full_art_button.hide()
        self.verticalLayout_5.addWidget(self.locate_full_art_button)
        self.verticalLayout_5.addSpacing(6)
        self.verticalLayout_5.addWidget(
            self.replaceButton, alignment=Qt.AlignmentFlag.AlignHCenter
        )
        self.verticalLayout_5.addWidget(self.restoreButton)

        secondary_actions = QHBoxLayout()
        secondary_actions.setSpacing(6)
        secondary_actions.addWidget(self.extractButton)
        secondary_actions.addWidget(self.copyButton)
        self.verticalLayout_5.addLayout(secondary_actions)

        text_actions = QHBoxLayout()
        text_actions.setSpacing(6)
        text_actions.addWidget(self.editButton)
        text_actions.addWidget(self.massEditButton)
        self.verticalLayout_5.addLayout(text_actions)
        self.verticalLayout_5.addWidget(self.favorite)
        self.verticalLayout_5.addStretch(1)

    def _build_results_header(self):
        self.resultsLabel = QLabel("Results", self)
        self.resultsLabel.setObjectName("resultsLabel")
        self.resultsLabel.setStyleSheet("font-weight: 600; color: #ffffff;")

        self.horizontalLayout.removeItem(self.horizontalSpacer_9)
        self.horizontalLayout.removeItem(self.horizontalSpacer_10)
        self.horizontalLayout.insertWidget(0, self.resultsLabel)
        self.horizontalLayout.setSpacing(8)
        self.horizontalLayout.setContentsMargins(0, 0, 0, 0)
        self.searchEdit.setMinimumHeight(32)
        self.searchButton.setMinimumHeight(32)
        self.searchButton.setMaximumWidth(42)
        self.horizontalLayout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        return self.horizontalLayout

    def _configure_results_grid(self):
        self.cardsView.setFlow(QListView.Flow.TopToBottom)
        self.cardsView.setWrapping(True)
        self.cardsView.setResizeMode(QListView.ResizeMode.Adjust)
        self.cardsView.setMovement(QListView.Movement.Static)
        self.cardsView.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.cardsView.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cardsView.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.cardsView.setToolTip(
            "Use Ctrl or Shift to select multiple cards for mass editing."
        )
        self.cardsView.setUniformItemSizes(True)
        self.cardsView.setWordWrap(True)
        self.cardsView.setIconSize(self.RESULT_ICON_SIZE)
        self.cardsView.setGridSize(self.RESULT_ITEM_SIZE)
        self.cardsView.setStyleSheet("""
            QListView::item {
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 4px;
            }
            QListView::item:selected {
                background: rgba(21, 160, 111, 0.24);
                border: 2px solid #15a06f;
            }
            QListView::item:focus {
                border: 2px solid #15a06f;
            }
            """)
        self._update_results_grid()

    def _update_results_grid(self):
        if not hasattr(self, "cardsView"):
            return

        viewport_height = max(1, self.cardsView.viewport().height())
        visible_rows = max(1, viewport_height // self.RESULT_ITEM_SIZE.height())
        self._visible_result_rows = visible_rows
        self.cardsView.setIconSize(self.RESULT_ICON_SIZE)
        self.cardsView.setGridSize(self.RESULT_ITEM_SIZE)
        self.cardsView.doItemsLayout()

    def _adjust_image_sizes(self):
        if not hasattr(self, "editorPanel"):
            super()._adjust_image_sizes()
            return

        if self.editorPanel.width() <= 0 or self.editorPanel.height() <= 0:
            return

        available_height = max(
            96, self.editorPanel.height() - 34 - self.image_fit.controls_height()
        )
        available_width = max(96, self.editorPanel.width() // 3)
        target_size = max(
            96,
            min(self._max_image_size, available_height, available_width),
        )

        for label, size in (
            (self.current, self._current_art_size),
            (self.preview, self._target_art_size),
        ):
            ratio = size[0] / size[1]
            height = min(target_size, int(target_size / ratio))
            label.setFixedSize(QSize(max(1, int(height * ratio)), height))
            label.updateGeometry()
            if label.parentWidget() is not self:
                label.parentWidget().setMinimumWidth(label.width())
                label.parentWidget().updateGeometry()

    def _queue_initial_layout_update(self):
        for delay in (0, 50, 150):
            QTimer.singleShot(delay, self._refresh_layout_after_show)

    def _queue_layout_update(self):
        QTimer.singleShot(0, self._refresh_layout_after_show)
        QTimer.singleShot(25, self._refresh_layout_after_show)

    def _refresh_layout_after_show(self):
        self.cardSplitter.updateGeometry()
        self.editorPanel.updateGeometry()
        self.resultsPanel.updateGeometry()
        self._adjust_image_sizes()
        self._update_results_grid()

    def _persist_splitter_state(self):
        self._settings.setValue("cards/splitter_state", self.cardSplitter.saveState())

    def _set_editor_context(self, text):
        self.bundle.setText(text)
        self.label.setText(f"Cards · {text}")

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

    def dropEvent(self, event: QDropEvent) -> None:
        """Handles the drop event of an image file."""
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif")):
                self._set_image(file_path)
                break

    def _set_image(self, file_path: str) -> None:
        if not self.image_fit.set_source(file_path):
            return
        self.cardEdit.setText(file_path)

    def _connect_callbacks(self):
        self.cardsView.clicked.connect(self._on_card_clicked)
        self.selectButton.clicked.connect(self._select_image)
        self.replaceButton.clicked.connect(self._replace)
        self.copyButton.clicked.connect(self._copy)
        self.extractButton.clicked.connect(self._extract_texture)
        self.searchButton.clicked.connect(self._search)
        self.restoreButton.clicked.connect(self._restore)
        self.editButton.clicked.connect(self._open_edit_modal)
        self.massEditButton.clicked.connect(self._open_mass_edit_modal)
        self.searchEdit.returnPressed.connect(self._search)
        self.searchEdit.textChanged.connect(self.searchHelperLabel.clear)
        self.favorite.stateChanged.connect(self._toggle_favorite)
        self.full_art_check.toggled.connect(self._toggle_full_art)
        self.locate_full_art_button.clicked.connect(self._locate_full_art)
        self.favorites.stateChanged.connect(self._toggle_favorites_filter)
        self.searchDescription.stateChanged.connect(self._toggle_description_search)
        self.searchBundle.stateChanged.connect(self._toggle_bundle_search)

        self.searchEdit.setCompleter(QCompleter(self.service.get_names()))
        self.searchEdit.completer().setCaseSensitivity(
            Qt.CaseSensitivity.CaseInsensitive
        )
        self.searchEdit.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.searchEdit.completer().activated.connect(self._search)

    def _toggle_favorite(self, state):
        if self.selected and self.selected.favorite != (
            state == Qt.CheckState.Checked.value
        ):
            self.selected.favorite = state == Qt.CheckState.Checked.value
            session.commit()
            show_toast(
                self,
                "Favorite",
                "Card favorite status updated",
                ToastPreset.SUCCESS_DARK,
            )

    def _toggle_favorites_filter(self, state):
        self.model.show_favorites = state == Qt.CheckState.Checked.value
        if self.model.show_favorites:
            self.model.refresh()
            self.model.layoutChanged.emit()
        elif len(self.searchEdit.text()) >= 3:
            self._search()

    def _toggle_description_search(self, state):
        self.model.search_description = state == Qt.CheckState.Checked.value
        if len(self.searchEdit.text()) >= 3:
            self._search()

    def _toggle_bundle_search(self, state):
        self.model.search_bundle = state == Qt.CheckState.Checked.value
        if len(self.searchEdit.text()) >= 3:
            self._search()

    def _open_edit_modal(self):
        if not self.selected:
            return

        dialog = CardEditDialog(self.selected)

        if dialog.exec():
            if dialog.get_action() == "regex":
                self._apply_regex_replacement(
                    *dialog.get_regex_inputs(), all_cards=False
                )
                return

            name, description = dialog.get_inputs()
            if name and description:
                # This is done in a pretty inefficient way, but one missing
                # card and the game can break, so everything needs to be
                # updated before any changes, in case of any CARD_* file update.
                try:
                    if name != remove_alt_tags(self.selected.name):
                        self.service.replace_name(name)
                    if description != self.selected.description:
                        self.service.replace_description(description)
                except (OSError, RuntimeError) as error:
                    logger.exception("Card text could not be saved")
                    show_toast(
                        self,
                        "Text Edit",
                        f"Card text could not be saved: {error}",
                        ToastPreset.ERROR_DARK,
                    )
                    return
                self.model.refresh()
                show_toast(
                    self,
                    "Text Edit",
                    "Card text edited successfully",
                    ToastPreset.SUCCESS_DARK,
                )

    def _open_mass_edit_modal(self):
        card_model = self.service._card_model()
        all_cards = session.query(card_model).order_by(card_model.name).all()
        selected_cards = [
            self.model.assets[index.row()]
            for index in self.cardsView.selectionModel().selectedIndexes()
        ]
        scopes = {
            "All cards": all_cards,
            "Selected cards": selected_cards,
            "Search results": (
                list(self.model.assets)
                if self.model.filter and not self.model.show_favorites
                else []
            ),
            "Favorites": [card for card in all_cards if card.favorite],
        }
        dialog = CardMassEditDialog(self, scopes=scopes)

        if dialog.exec():
            self._apply_regex_replacement(
                *dialog.get_inputs(),
                all_cards=False,
                cards=dialog.get_cards(),
                scope=dialog.scope_input.currentData(),
            )

    def _apply_regex_replacement(
        self,
        pattern,
        replacement,
        replace_names,
        replace_descriptions,
        all_cards,
        cards=None,
        scope=None,
    ):

        if all_cards and not show_confirmation_dialog(
            "Apply this regex replacement to all cards?", True
        ):
            return

        try:
            changed_cards, replacements = self.service.replace_text_with_regex(
                pattern,
                replacement,
                replace_names,
                replace_descriptions,
                None if all_cards else self.selected,
                cards=cards,
            )
        except (OSError, RuntimeError, ValueError, IndexError, re.error) as error:
            logger.exception("Card regular-expression replacement failed")
            show_toast(
                self,
                "Regex replacement",
                f"Could not apply regex: {error}",
                ToastPreset.ERROR_DARK,
            )
            return

        if not changed_cards:
            show_toast(
                self,
                "Regex replacement",
                "No matching card text found",
                ToastPreset.WARNING_DARK,
            )
            return

        self.model.refresh()
        scope = scope or ("all cards" if all_cards else "the selected card")
        show_toast(
            self,
            "Regex replacement",
            f"Replaced {replacements} match(es) across {changed_cards} card(s) in {scope}",
            ToastPreset.SUCCESS_DARK,
        )

    def _restore(self):
        if self.service.restore_asset():
            self.model.refresh()
            self._refresh_art_context()
            self._refresh_current_art()
            show_toast(
                self, "Backup", "Card restored successfully", ToastPreset.SUCCESS_DARK
            )
        else:
            show_toast(
                self, "Backup", "Card backup not found", ToastPreset.WARNING_DARK
            )

    def _on_card_clicked(self, index):
        self.selected = self.model.assets[index.row()]
        self.service.bundle = self.selected.bundle
        self.service.unity_file = self.selected.unity_file
        self._refresh_art_context()
        self._refresh_current_art()

        modded_name = (
            f"- <i style='color:#ccffcc'>{self.selected.modded_name}</i> "
            if self.selected.modded_name
            else ""
        )
        self._set_editor_context(
            f"Editing {self.model.assets[index.row()].name} {modded_name}({self.selected.bundle})"
        )

        self.replaceButton.setEnabled(True)
        self.extractButton.setEnabled(True)
        self.restoreButton.setEnabled(True)
        self.copyButton.setEnabled(True)
        self.editButton.setEnabled(True)
        self.favorite.setChecked(self.selected.favorite)
        hide_selection_helper(self)

    def _refresh_current_art(self):
        icon = fetch_bundle_thumb(self.service.bundle, None, self.service.unity_file)
        if icon:
            self.current.setPixmap(icon.pixmap(*self._current_art_size))

    def _refresh_art_context(self):
        self._art_id, self._current_art_size = self.service.get_art_details()
        full_art, can_toggle = False, False
        self.locate_full_art_button.hide()
        message = ""
        if self._art_id is not None:
            try:
                full_art, can_toggle = self.service.full_art.status(
                    APP_CONFIG.game_path, self._art_id
                )
            except (OSError, RuntimeError, ValueError) as error:
                logger.warning("Could not read overframe status: %s", error)
                self.locate_full_art_button.show()
                message = (
                    "Overframe status unavailable; using current texture dimensions."
                )
        else:
            message = "Overframe switch unavailable for this texture."
        self.full_art_check.blockSignals(True)
        self.full_art_check.setChecked(full_art)
        self.full_art_check.setEnabled(can_toggle)
        self.full_art_check.blockSignals(False)
        if full_art:
            self._target_art_size = (704, 1024)
        elif can_toggle and self._current_art_size == (704, 1024):
            self._target_art_size = (512, 512)
        else:
            self._target_art_size = self._current_art_size
        width, height = self._target_art_size
        self.art_size_label.setText(
            message
            or f"{'Overframe' if full_art else 'Normal art'} · {width} × {height}"
        )
        self.image_fit.refresh_target_size()
        self._adjust_image_sizes()

    def _toggle_full_art(self, enabled):
        if not self.selected or self._art_id is None:
            return
        try:
            self.service.full_art.set_enabled(
                APP_CONFIG.game_path, self._art_id, enabled, APP_CONFIG.packer
            )
        except (OSError, RuntimeError, ValueError) as error:
            logger.exception("Overframe setting could not be saved")
            show_toast(
                self,
                "Overframe",
                f"Could not change overframe setting: {error}",
                ToastPreset.ERROR_DARK,
            )
        else:
            show_toast(
                self,
                "Overframe",
                "Card framing updated. Replace artwork to apply the preview.",
                ToastPreset.SUCCESS_DARK,
            )
        self._refresh_art_context()

    def _locate_full_art(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select the of_card_asset bundle",
            APP_CONFIG.game_path,
            "Asset bundles (*)",
        )
        if not path:
            return
        try:
            self.service.full_art.select_path(path, APP_CONFIG.game_path)
        except (OSError, RuntimeError, ValueError) as error:
            show_toast(self, "Overframe", str(error), ToastPreset.ERROR_DARK)
            return
        self._refresh_art_context()

    def _select_image(self):
        file, _ = QFileDialog.getOpenFileUrl(self, "Select Image", "", IMAGE_FILTER)

        if file and file.url() != "":
            local_file = file.toLocalFile()

            self._set_image(local_file)

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
        if not self.selected or not self.service.image_path:
            show_toast(
                self,
                "Card",
                "Select a card and a replacement image first.",
                ToastPreset.WARNING_DARK,
            )
            return
        if APP_CONFIG.create_backup and not self.selected.has_backup:
            self.service.create_backup(self.service.bundle)
            self.model.set_backup_state(self.selected.id, True)

        self.service.replace_bundle()
        self.model.refresh()
        self._refresh_art_context()
        self._refresh_current_art()

        show_toast(
            self, "Card", "Card replacement successful", ToastPreset.SUCCESS_DARK
        )

    def _search(self):
        search_filter = self.searchEdit.text()

        if not self.model.show_favorites:
            if len(search_filter) >= 3:
                self.searchHelperLabel.clear()
                self.model.filter = search_filter
                self.model.refresh()
                self.model.layoutChanged.emit()
            else:
                self.searchHelperLabel.setText("Enter at least 3 characters to search.")
                show_toast(
                    self,
                    "Search",
                    "Please use 3 or more characters to search",
                    ToastPreset.INFORMATION_DARK,
                )
