"""Responsive deck box editor with automatic resolution handling."""

from PySide6 import QtWidgets
from PySide6.QtCore import Qt, QSize, QSettings, QTimer
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QComboBox,
    QMessageBox,
    QHBoxLayout,
    QLabel,
    QListView,
    QLayout,
    QSizePolicy,
    QVBoxLayout,
)
from pyqttoast import ToastPreset

from database.objects import session
from widgets.grip_splitter import GripSplitter
from pages.base_responsive_page import ResponsivePageMixin
from pages.models.deck_box_list_model import DeckBoxListModel
from pages.ui.deck_box import Ui_DeckBox
from services.deck_box_service import DeckBoxService, DECK_BOX_VARIANTS
from unity.unity_utils import fetch_bundle_thumb
from util.constants import IMAGE_FILTER, APP_CONFIG
from util.ui_util import show_toast
from widgets.ux import configure_editor_chrome, hide_selection_helper, set_button_roles
from widgets.image_fit import InlineImageFitController


class DeckBox(ResponsivePageMixin, QtWidgets.QWidget, Ui_DeckBox):
    """Edit deck box orientations with the shared editor layout."""

    RESULT_ITEM_SIZE = QSize(116, 132)
    RESULT_ICON_SIZE = QSize(96, 96)
    RESULTS_MIN_HEIGHT = 315

    def __init__(self):
        QtWidgets.QWidget.__init__(self)
        ResponsivePageMixin.__init__(self)
        self.setupUi(self)
        placeholder = QIcon(":/ui/images/deck_box.svg").pixmap(512, 512)
        self.current.setPixmap(placeholder)
        self.preview.setPixmap(placeholder)

        # Configure responsive images with aspect ratio
        self.setup_responsive_images(
            self.current,
            self.preview,
            aspect_ratio=(256, 256),
            max_image_size=500,
            min_image_size=64,
        )

        self.service = DeckBoxService()
        self.model = DeckBoxListModel()
        self.deck_boxesView.setModel(self.model)
        self.selected = None
        self._texture_size = (512, 512)
        self._settings = QSettings("Floowandereeze", "FloowandereezeAndModding")
        configure_editor_chrome(
            self,
            current_widget=self.current,
            preview_widget=self.preview,
            file_edits=(self.assetEdit,),
            list_views=(self.deck_boxesView,),
            helper_after=self.bundle,
        )
        self.image_fit = InlineImageFitController(
            self,
            self.preview,
            lambda: self._texture_size,
            lambda image_path: setattr(self.service, "image_path", image_path),
            alignment_widget=self.current,
        )
        set_button_roles(self)
        self._configure_split_layout()
        self._set_editor_context("Select a Deck Box")
        self._configure_results_grid()
        self._queue_initial_layout_update()

        # Enable drag and drop
        self.setAcceptDrops(True)

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
            self.favoritesLayout,
        ):
            self.verticalLayout.removeItem(layout)
        self.verticalLayout.removeWidget(self.deck_boxesView)

        self._configure_editor_controls()

        self.editorPanel = QtWidgets.QWidget(self)
        self.editorPanel.setObjectName("deck_boxEditorPanel")
        self.editorPanel.setMinimumHeight(230)
        editor_layout = QVBoxLayout(self.editorPanel)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(8)
        editor_layout.addLayout(self.main_content)

        self.resultsPanel = QtWidgets.QWidget(self)
        self.resultsPanel.setObjectName("deck_boxResultsPanel")
        self.resultsPanel.setMinimumHeight(self.RESULTS_MIN_HEIGHT)
        results_layout = QVBoxLayout(self.resultsPanel)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.setSpacing(6)
        results_layout.addLayout(self._build_results_header())
        results_layout.addWidget(self.deck_boxesView, 1)

        self.deck_boxSplitter = GripSplitter(Qt.Orientation.Vertical, self)
        self.deck_boxSplitter.setObjectName("deck_boxSplitter")
        self.deck_boxSplitter.setChildrenCollapsible(False)
        self.deck_boxSplitter.setOpaqueResize(True)
        self.deck_boxSplitter.addWidget(self.editorPanel)
        self.deck_boxSplitter.addWidget(self.resultsPanel)
        self.deck_boxSplitter.setStretchFactor(0, 3)
        self.deck_boxSplitter.setStretchFactor(1, 2)
        self.deck_boxSplitter.splitterMoved.connect(self._persist_splitter_state)
        self.deck_boxSplitter.splitterMoved.connect(lambda *_: self._queue_layout_update())

        stored_state = self._settings.value("deck_boxes/splitter_state")
        if stored_state:
            self.deck_boxSplitter.restoreState(stored_state)
        else:
            self.deck_boxSplitter.setSizes([520, 360])

        self.verticalLayout.addWidget(self.deck_boxSplitter, 1)

    def _configure_editor_controls(self):
        self.label_4.setText("Image source")
        self.label_4.setStyleSheet("font-weight: 600; color: #ffffff;")
        self.assetEdit.setMinimumWidth(210)
        self.assetEdit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

        for layout, widget in (
            (self.verticalLayout_2, self.label_4),
            (self.verticalLayout_3, self.assetEdit),
            (self.verticalLayout_4, self.selectButton),
            (self.horizontalLayout_4, self.restoreButton),
            (self.horizontalLayout_4, self.extractButton),
            (self.horizontalLayout_4, self.copyButton),
            (self.horizontalLayout_4, self.replaceButton),
            (self.favoritesLayout, self.favoriteBox),
        ):
            layout.removeWidget(widget)

        self.verticalLayout_5.setSpacing(8)
        self.verticalLayout_5.setContentsMargins(0, 26, 0, 0)
        self.verticalLayout_5.addStretch(1)
        self.variantLabel = QLabel("Texture variant", self)
        self.variantBox = QComboBox(self)
        for label, key in DECK_BOX_VARIANTS:
            self.variantBox.addItem(label, key)
        self.variantBox.setCurrentIndex(0)
        self.variantBox.setEnabled(False)
        self.verticalLayout_5.addWidget(self.variantLabel)
        self.verticalLayout_5.addWidget(self.variantBox)
        self.verticalLayout_5.addWidget(self.label_4)
        self.verticalLayout_5.addWidget(self.assetEdit)
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

        self.verticalLayout_5.addWidget(self.favoriteBox)
        self.verticalLayout_5.addStretch(1)

    def _build_results_header(self):
        self.resultsLabel = QLabel("Results", self)
        self.resultsLabel.setObjectName("resultsLabel")
        self.resultsLabel.setStyleSheet("font-weight: 600; color: #ffffff;")

        self.favoritesLayout.removeItem(self.horizontalSpacer_9)
        self.favoritesLayout.removeItem(self.horizontalSpacer_10)
        self.favoritesLayout.removeItem(self.horizontalSpacer_11)
        self.favoritesLayout.insertWidget(0, self.resultsLabel)
        self.favoritesLayout.setSpacing(8)
        self.favoritesLayout.setContentsMargins(0, 0, 0, 0)
        self.favoritesLayout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        return self.favoritesLayout

    def _configure_results_grid(self):
        self.deck_boxesView.setFlow(QListView.Flow.TopToBottom)
        self.deck_boxesView.setWrapping(True)
        self.deck_boxesView.setResizeMode(QListView.ResizeMode.Adjust)
        self.deck_boxesView.setMovement(QListView.Movement.Static)
        self.deck_boxesView.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.deck_boxesView.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.deck_boxesView.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.deck_boxesView.setUniformItemSizes(True)
        self.deck_boxesView.setWordWrap(True)
        self.deck_boxesView.setIconSize(self.RESULT_ICON_SIZE)
        self.deck_boxesView.setGridSize(self.RESULT_ITEM_SIZE)
        self.deck_boxesView.setStyleSheet("""
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
        if not hasattr(self, "deck_boxesView"):
            return

        self.deck_boxesView.setIconSize(self.RESULT_ICON_SIZE)
        self.deck_boxesView.setGridSize(self.RESULT_ITEM_SIZE)
        self.deck_boxesView.doItemsLayout()

    def _adjust_image_sizes(self):
        if not hasattr(self, "editorPanel"):
            super()._adjust_image_sizes()
            return

        if self.editorPanel.width() <= 0 or self.editorPanel.height() <= 0:
            return

        available_height = max(
            64, self.editorPanel.height() - 34 - self.image_fit.controls_height()
        )
        available_width = max(64, self.editorPanel.width() // 3)
        ratio = self._texture_size[0] / self._texture_size[1]
        target_height = max(
            64,
            min(self._max_image_size, available_height, int(available_width / ratio)),
        )
        for label in (self.current, self.preview):
            label.setFixedSize(QSize(int(target_height * ratio), target_height))
            label.updateGeometry()

    def _queue_initial_layout_update(self):
        for delay in (0, 50, 150):
            QTimer.singleShot(delay, self._refresh_layout_after_show)

    def _queue_layout_update(self):
        QTimer.singleShot(0, self._refresh_layout_after_show)
        QTimer.singleShot(25, self._refresh_layout_after_show)

    def _refresh_layout_after_show(self):
        self.deck_boxSplitter.updateGeometry()
        self.editorPanel.updateGeometry()
        self.resultsPanel.updateGeometry()
        self._adjust_image_sizes()
        self._update_results_grid()

    def _persist_splitter_state(self):
        self._settings.setValue("deck_boxes/splitter_state", self.deck_boxSplitter.saveState())

    def _set_editor_context(self, text):
        self.bundle.setText(text)
        self.label.setText(f"Deck Boxes · {text}")

    def _connect_callbacks(self):
        self.variantBox.currentIndexChanged.connect(self._update_variant)
        self.deck_boxesView.clicked.connect(self._on_deck_box_clicked)
        self.selectButton.clicked.connect(self._select_image)
        self.replaceButton.clicked.connect(self._replace)
        self.copyButton.clicked.connect(self._copy)
        self.extractButton.clicked.connect(self._extract_texture)
        self.restoreButton.clicked.connect(self._restore)
        self.favoriteBox.stateChanged.connect(self._toggle_favorite)
        self.favoritesBox.stateChanged.connect(self._toggle_favorites_filter)

    def _restore(self):
        if self.service.restore_variant():
            self.model.refresh()
            self._update_variant()
            show_toast(
                self, "Backup", "Deck box variant restored", ToastPreset.SUCCESS_DARK
            )
        else:
            show_toast(
                self, "Backup", "Deck box variant backup not found",
                ToastPreset.WARNING_DARK,
            )

    def _on_deck_box_clicked(self, index):
        if not index.isValid():
            return
        self.selected = self.model.assets[index.row()]
        self.variantBox.setEnabled(True)
        self.favoriteBox.setEnabled(True)
        self.favoriteBox.setChecked(self.selected.favorite)
        self._update_variant()
        hide_selection_helper(self)

    def _update_variant(self, *_):
        if self.selected is None:
            return
        self.service.select_variant(self.selected, self.variantBox.currentData())
        for button in (
            self.replaceButton, self.extractButton, self.restoreButton, self.copyButton
        ):
            button.setEnabled(False)
        self.current.clear()
        self._set_editor_context(
            f"Editing {self.selected.name} · {self.variantBox.currentText()}"
        )
        if not self.service.bundle:
            return
        try:
            self._texture_size = self.service.texture_size()
            thumbnail = fetch_bundle_thumb(self.service.bundle, None)
            if thumbnail is None:
                raise ValueError("No texture found in this variant")
            self.current.setPixmap(thumbnail.pixmap(*self._texture_size))
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Deck Box", f"Could not load this variant:\n{error}")
            return
        self.image_fit.refresh_target_size()
        self._adjust_image_sizes()
        self.extractButton.setEnabled(True)
        self.restoreButton.setEnabled(True)
        self.copyButton.setEnabled(True)
        self.replaceButton.setEnabled(bool(self.service.image_path))

    def _copy(self):
        self.service.copy_bundle()
        show_toast(
            self,
            "Deck Box Copying",
            'Deck box variant copied to "bundles/deck_boxes"',
            ToastPreset.SUCCESS_DARK,
        )

    def _select_image(self):
        file, _ = QFileDialog.getOpenFileUrl(self, "Select Image", "", IMAGE_FILTER)

        if file and file.url() != "":
            local_file = file.toLocalFile()

            self._set_image(local_file)

    def _set_image(self, file_path: str) -> None:
        if not self.image_fit.set_source(file_path):
            return
        self.assetEdit.setText(file_path)
        self.replaceButton.setEnabled(self.extractButton.isEnabled())

    def _extract_texture(self):
        self.service.extract_texture(self.service.bundle)
        show_toast(
            self, "Deck Box Extraction", 'Variant extracted to "images/deck_boxes"',
            ToastPreset.SUCCESS_DARK,
        )

    def _replace(self):
        if not self.selected or not self.service.image_path:
            return
        if APP_CONFIG.create_backup:
            self.service.ensure_backup()
            self.model.set_backup_state(self.selected.id, True)
            session.commit()
        self.service.replace_bundle()
        self.model.refresh()
        self._update_variant()
        show_toast(
            self, "Deck Box", "Deck box variant replacement successful",
            ToastPreset.SUCCESS_DARK,
        )

    def _toggle_favorite(self, state):
        if self.selected and self.selected.favorite != (
            state == Qt.CheckState.Checked.value
        ):
            self.selected.favorite = state == Qt.CheckState.Checked.value
            session.commit()
            show_toast(
                self,
                "Favorite",
                "Deck box favorite status updated",
                ToastPreset.SUCCESS_DARK,
            )

    def _toggle_favorites_filter(self, state):
        self.model.show_favorites = state == Qt.CheckState.Checked.value
        self.model.refresh()

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
