from typing_extensions import Optional
from PySide6.QtCore import Qt, QSize, QSettings
from PySide6.QtGui import QPixmap, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QCompleter,
    QHBoxLayout,
    QLabel,
    QListView,
    QLayout,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from pyqttoast import ToastPreset

from database.models import CardModel
from database.objects import session
from dialogs.card_edit_dialog import CardEditDialog
from pages.base_responsive_page import ResponsivePageMixin
from pages.models.card_list_model import CardListModel
from pages.ui.card import Ui_Card
from services.card_service import CardService
from unity.unity_utils import fetch_bundle_thumb
from util.constants import IMAGE_FILTER, APP_CONFIG
from util.python_utils import remove_alt_tags
from util.ui_util import show_toast
from widgets.ux import configure_editor_chrome, hide_selection_helper, set_button_roles


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
            max_image_size=340,
        )

        self.service = CardService()
        self.model = CardListModel()
        self.cardsView.setModel(self.model)
        self.selected: Optional[CardModel] = None
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
        set_button_roles(self)
        self._configure_split_layout()
        self.searchEdit.setPlaceholderText("Search cards, min 3 characters")
        self._set_editor_context("Select a Card")
        self._configure_results_grid()

        # Enable drag and drop
        self.setAcceptDrops(True)

        # Initialize the model's search_description property
        self.model.search_description = False

        self._connect_callbacks()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_results_grid()

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

        self.cardSplitter = QSplitter(Qt.Orientation.Vertical, self)
        self.cardSplitter.setObjectName("cardSplitter")
        self.cardSplitter.setChildrenCollapsible(False)
        self.cardSplitter.setOpaqueResize(True)
        self.cardSplitter.addWidget(self.editorPanel)
        self.cardSplitter.addWidget(self.resultsPanel)
        self.cardSplitter.setStretchFactor(0, 3)
        self.cardSplitter.setStretchFactor(1, 2)
        self.cardSplitter.splitterMoved.connect(self._persist_splitter_state)
        self.cardSplitter.splitterMoved.connect(lambda *_: self._adjust_image_sizes())
        self.cardSplitter.splitterMoved.connect(lambda *_: self._update_results_grid())

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

        self.verticalLayout_5.addWidget(self.editButton)
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
        self.cardsView.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
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

        available_height = max(96, self.editorPanel.height() - 34)
        available_width = max(96, self.editorPanel.width() // 3)
        target_size = max(
            96,
            min(self._max_image_size, available_height, available_width),
        )

        for label in (self.current, self.preview):
            label.setFixedSize(QSize(target_size, target_size))
            label.updateGeometry()

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
                self.cardEdit.setText(file_path)
                self.preview.setPixmap(QPixmap(file_path))
                self.service.image_path = file_path
                break

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
        self.searchEdit.textChanged.connect(lambda: self.searchHelperLabel.clear())
        self.favorite.stateChanged.connect(self._toggle_favorite)
        self.favorites.stateChanged.connect(self._toggle_favorites_filter)
        self.searchDescription.stateChanged.connect(self._toggle_description_search)

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

    def _open_edit_modal(self):
        dialog = CardEditDialog(self.selected)

        if dialog.exec():
            name, description = dialog.get_inputs()
            if name and description:
                # This is done in a pretty inefficient way, but one missing
                # card and the game can break, so everything needs to be
                # updated before any changes, in case of any CARD_* file update.
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
