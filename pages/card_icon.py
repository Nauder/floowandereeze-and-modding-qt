"""Card Icon Page Module.

This module provides the card icon modding page for the application.
It allows users to modify card icons from the sprite atlas.
"""

from io import BytesIO
from typing import Optional

from PIL import Image
from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import QSize, QSettings, QTimer
from PySide6.QtGui import QPixmap, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListView,
    QLayout,
    QSizePolicy,
    QVBoxLayout,
)
from pyqttoast import ToastPreset

from database.models import CardIconModel
from widgets.grip_splitter import GripSplitter
from pages.base_responsive_page import ResponsivePageMixin
from pages.models.card_icon_list_model import CardIconListModel
from pages.ui.card_icon import Ui_CardIcon
from services.card_icon_service import CardIconService
from util.constants import IMAGE_FILTER, APP_CONFIG
from util.ui_util import show_toast
from widgets.ux import configure_editor_chrome, hide_selection_helper, set_button_roles
from widgets.image_fit import InlineImageFitController


class CardIcon(ResponsivePageMixin, QtWidgets.QWidget, Ui_CardIcon):
    """
    Card icon modding page.

    This page allows users to modify card icons from the sprite atlas.
    It provides functionality to select, preview, replace, extract, and restore card icons.
    """

    RESULT_ITEM_SIZE = QSize(116, 132)
    RESULT_ICON_SIZE = QSize(96, 96)
    RESULTS_MIN_HEIGHT = 315

    def __init__(self):
        QtWidgets.QWidget.__init__(self)
        ResponsivePageMixin.__init__(self)
        self.setupUi(self)

        # Configure responsive images with aspect ratio
        self.setup_responsive_images(
            self.current,
            self.preview,
            aspect_ratio=(374, 374),
            max_image_size=250,
            min_image_size=128,
        )

        self.service = CardIconService()
        self.model = CardIconListModel()
        self.iconsList.setModel(self.model)
        self.selected: Optional[CardIconModel] = None
        self._settings = QSettings("Floowandereeze", "FloowandereezeAndModding")
        configure_editor_chrome(
            self,
            current_widget=self.current,
            preview_widget=self.preview,
            file_edits=(self.iconEdit,),
            list_views=(self.iconsList,),
            helper_after=self.bundle,
        )
        self.image_fit = InlineImageFitController(
            self,
            self.preview,
            lambda: (
                (self.selected.width, self.selected.height)
                if self.selected
                else (0, 0)
            ),
            lambda image_path: setattr(self.service, "image_path", image_path),
            alignment_widget=self.current,
        )
        set_button_roles(self)
        self._configure_split_layout()
        self._set_editor_context("Select a Card Icon")
        self._configure_results_grid()
        self._queue_initial_layout_update()

        # Enable drag and drop
        self.setAcceptDrops(True)

        self._connect_callbacks()

    def resizeEvent(self, event: QtCore.QEvent) -> None:
        super().resizeEvent(event)
        self._update_results_grid()

    def showEvent(self, event: QtCore.QEvent) -> None:
        super().showEvent(event)
        self._queue_initial_layout_update()

    def _configure_split_layout(self) -> None:
        self.verticalLayout.setSpacing(8)
        self.verticalLayout.setContentsMargins(12, 8, 12, 12)
        self.label.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        self.label.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.bundle.hide()
        self.current_label.show()
        self.preview_label.show()
        for label in (self.current_label, self.preview_label):
            label.setStyleSheet("font-weight: 600; color: #ffffff;")

        for helper_label_name in ("currentHeaderLabel", "previewHeaderLabel"):
            helper_label = self.findChild(QLabel, helper_label_name)
            if helper_label:
                helper_label.hide()

        for layout in (
            self.main_content,
            self.controls_layout,
            self.horizontalLayout,
        ):
            self.verticalLayout.removeItem(layout)

        self._configure_editor_controls()

        self.editorPanel = QtWidgets.QWidget(self)
        self.editorPanel.setObjectName("cardIconEditorPanel")
        self.editorPanel.setMinimumHeight(230)
        editor_layout = QVBoxLayout(self.editorPanel)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(8)
        editor_layout.addLayout(self.main_content)

        self.resultsPanel = QtWidgets.QWidget(self)
        self.resultsPanel.setObjectName("cardIconResultsPanel")
        self.resultsPanel.setMinimumHeight(self.RESULTS_MIN_HEIGHT)
        results_layout = QVBoxLayout(self.resultsPanel)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.setSpacing(6)
        results_layout.addLayout(self._build_results_header())
        results_layout.addWidget(self.iconsList, 1)

        self.cardIconSplitter = GripSplitter(QtCore.Qt.Orientation.Vertical, self)
        self.cardIconSplitter.setObjectName("cardIconSplitter")
        self.cardIconSplitter.setChildrenCollapsible(False)
        self.cardIconSplitter.setOpaqueResize(True)
        self.cardIconSplitter.addWidget(self.editorPanel)
        self.cardIconSplitter.addWidget(self.resultsPanel)
        self.cardIconSplitter.setStretchFactor(0, 3)
        self.cardIconSplitter.setStretchFactor(1, 2)
        self.cardIconSplitter.splitterMoved.connect(self._persist_splitter_state)
        self.cardIconSplitter.splitterMoved.connect(
            lambda *_: self._queue_layout_update()
        )

        stored_state = self._settings.value("card_icons/splitter_state")
        if stored_state:
            self.cardIconSplitter.restoreState(stored_state)
        else:
            self.cardIconSplitter.setSizes([520, 360])

        self.verticalLayout.addWidget(self.cardIconSplitter, 1)

    def _configure_editor_controls(self) -> None:
        self.file_label.setText("Image source")
        self.file_label.setStyleSheet("font-weight: 600; color: #ffffff;")
        self.iconEdit.setMinimumWidth(210)
        self.iconEdit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

        for layout, widget in (
            (self.file_layout, self.file_label),
            (self.file_layout, self.iconEdit),
            (self.file_layout, self.selectButton),
            (self.buttons_layout, self.replaceButton),
            (self.buttons_layout, self.extractButton),
            (self.buttons_layout, self.restoreButton),
        ):
            layout.removeWidget(widget)

        controls_layout = QVBoxLayout()
        controls_layout.setObjectName("cardIconEditorControls")
        controls_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        controls_layout.setSpacing(8)
        controls_layout.setContentsMargins(0, 26, 0, 0)
        controls_layout.addStretch(1)
        controls_layout.addWidget(self.file_label)
        controls_layout.addWidget(self.iconEdit)
        controls_layout.addWidget(self.selectButton)
        controls_layout.addSpacing(6)
        controls_layout.addWidget(
            self.replaceButton, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter
        )
        controls_layout.addWidget(self.restoreButton)

        secondary_actions = QHBoxLayout()
        secondary_actions.setSpacing(6)
        secondary_actions.addWidget(self.extractButton)
        controls_layout.addLayout(secondary_actions)
        controls_layout.addStretch(1)

        self.main_content.insertLayout(3, controls_layout)
        self.main_content.insertItem(
            4,
            QtWidgets.QSpacerItem(
                20,
                20,
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Minimum,
            ),
        )
        self.main_content.setStretch(0, 1)
        self.main_content.setStretch(1, 3)
        self.main_content.setStretch(2, 1)
        self.main_content.setStretch(3, 1)
        self.main_content.setStretch(4, 1)
        self.main_content.setStretch(5, 3)
        self.main_content.setStretch(6, 1)

    def _build_results_header(self):
        self.resultsLabel = QLabel("Results", self)
        self.resultsLabel.setObjectName("resultsLabel")
        self.resultsLabel.setStyleSheet("font-weight: 600; color: #ffffff;")

        self.horizontalLayout.removeItem(self.horizontalSpacer_6)
        self.horizontalLayout.removeItem(self.horizontalSpacer_9)
        self.horizontalLayout.insertWidget(0, self.resultsLabel)
        self.horizontalLayout.setSpacing(8)
        self.horizontalLayout.setContentsMargins(0, 0, 0, 0)
        self.horizontalLayout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        return self.horizontalLayout

    def _configure_results_grid(self) -> None:
        self.iconsList.setFlow(QListView.Flow.TopToBottom)
        self.iconsList.setWrapping(True)
        self.iconsList.setResizeMode(QListView.ResizeMode.Adjust)
        self.iconsList.setMovement(QListView.Movement.Static)
        self.iconsList.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.iconsList.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.iconsList.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.iconsList.setUniformItemSizes(True)
        self.iconsList.setWordWrap(True)
        self.iconsList.setTextElideMode(QtCore.Qt.TextElideMode.ElideRight)
        self.iconsList.setIconSize(self.RESULT_ICON_SIZE)
        self.iconsList.setGridSize(self.RESULT_ITEM_SIZE)
        self.iconsList.setStyleSheet("""
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

    def _update_results_grid(self) -> None:
        if not hasattr(self, "iconsList"):
            return

        self.iconsList.setIconSize(self.RESULT_ICON_SIZE)
        self.iconsList.setGridSize(self.RESULT_ITEM_SIZE)
        self.iconsList.doItemsLayout()

    def _adjust_image_sizes(self) -> None:
        if not hasattr(self, "editorPanel"):
            super()._adjust_image_sizes()
            return

        if self.editorPanel.width() <= 0 or self.editorPanel.height() <= 0:
            return

        available_height = max(
            128, self.editorPanel.height() - 34 - self.image_fit.controls_height()
        )
        available_width = max(128, self.editorPanel.width() // 3)
        target_size = max(
            128,
            min(self._max_image_size, available_height, available_width),
        )

        for label in (self.current, self.preview):
            label.setFixedSize(QSize(target_size, target_size))
            label.updateGeometry()

    def _queue_initial_layout_update(self) -> None:
        for delay in (0, 50, 150):
            QTimer.singleShot(delay, self._refresh_layout_after_show)

    def _queue_layout_update(self) -> None:
        QTimer.singleShot(0, self._refresh_layout_after_show)
        QTimer.singleShot(25, self._refresh_layout_after_show)

    def _refresh_layout_after_show(self) -> None:
        self.cardIconSplitter.updateGeometry()
        self.editorPanel.updateGeometry()
        self.resultsPanel.updateGeometry()
        self._adjust_image_sizes()
        self._update_results_grid()

    def _persist_splitter_state(self) -> None:
        self._settings.setValue(
            "card_icons/splitter_state", self.cardIconSplitter.saveState()
        )

    def _set_editor_context(self, text: str) -> None:
        self.bundle.setText(text)
        self.label.setText(f"Card Icons · {text}")

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
        if not self.selected:
            show_toast(
                self,
                "Card Icon",
                "Select a card icon before choosing its replacement image",
                ToastPreset.WARNING_DARK,
            )
            return
        if not self.image_fit.set_source(file_path):
            return
        self.iconEdit.setText(file_path)
        self._check_replace_button()

    def _connect_callbacks(self):
        """Connect UI callbacks to their respective methods."""
        self.iconsList.clicked.connect(self._on_icon_clicked)
        self.selectButton.clicked.connect(self._select_image)
        self.replaceButton.clicked.connect(self._replace_icon)
        self.extractButton.clicked.connect(self._extract_texture)
        self.restoreButton.clicked.connect(self._restore)

    def _on_icon_clicked(self, index):
        """Handle icon selection from the list."""
        self.selected = self.model.assets[index.row()]
        self.service.selected_icon = self.selected
        self.image_fit.refresh_target_size()

        # Update UI
        self._set_editor_context(f"Editing {self.selected.name}")

        # Load current icon display
        self._load_current_icon_display()

        # Enable buttons
        self.extractButton.setEnabled(True)
        self.restoreButton.setEnabled(True)
        self._check_replace_button()
        hide_selection_helper(self)

    def _load_current_icon_display(self) -> None:
        """Load and display the current icon from the sprite atlas."""
        try:
            if not self.selected:
                self.current.setText("No Icon")
                return

            atlas_img = self.model.atlas_image

            # Extract the icon region
            icon_img = atlas_img.crop(
                (
                    self.selected.x,
                    self.selected.y,
                    self.selected.x + self.selected.width,
                    self.selected.y + self.selected.height,
                )
            )

            # Resize for display
            icon_img = icon_img.resize((128, 128), Image.Resampling.LANCZOS)

            # Convert to QPixmap
            img_bytes = BytesIO()
            icon_img.save(img_bytes, format="PNG")
            img_bytes.seek(0)
            pixmap = QPixmap()
            pixmap.loadFromData(img_bytes.getvalue())

            self.current.setPixmap(pixmap)
            return

        except Exception as e:
            print(f"Error loading current icon display: {e}")
            self.current.setText("Error loading icon")

    def _select_image(self):
        """Select image file for replacement."""
        file, _ = QFileDialog.getOpenFileUrl(
            self, "Select Icon Image", "", IMAGE_FILTER
        )

        if file and file.url() != "":
            local_file = file.toLocalFile()
            self._set_image(local_file)

    def _check_replace_button(self):
        """Enable replace button if conditions are met."""
        has_image = bool(self.service.image_path)
        has_selection = bool(self.selected)
        self.replaceButton.setEnabled(has_image and has_selection)

    def _extract_texture(self):
        """Extract the current icon texture."""
        if not self.selected:
            show_toast(
                self,
                "Extract",
                "No icon selected",
                ToastPreset.WARNING_DARK,
            )
            return

        try:
            self.service.extract_texture(self.selected.name)
            show_toast(
                self,
                "Icon Extraction",
                f'Icon "{self.selected.name}" extracted to the "icons" folder',
                ToastPreset.SUCCESS_DARK,
            )
        except Exception as e:
            show_toast(
                self,
                "Icon Extraction",
                f"Icon extraction failed: {str(e)}",
                ToastPreset.ERROR_DARK,
            )

    def _restore(self):
        """Restore icon from backup."""
        if not self.selected:
            show_toast(
                self,
                "Restore",
                "No icon selected",
                ToastPreset.WARNING_DARK,
            )
            return

        if self.service.restore_asset(self.selected.name):
            # Refresh displays
            self.model.refresh(force_reload=True)
            self._load_current_icon_display()
            show_toast(
                self,
                "Backup",
                f'Icon "{self.selected.name}" restored successfully',
                ToastPreset.SUCCESS_DARK,
            )
        else:
            show_toast(
                self,
                "Backup",
                f'Icon "{self.selected.name}" backup not found',
                ToastPreset.WARNING_DARK,
            )

    def _replace_icon(self):
        """Replace the selected icon with the chosen image."""
        if not self.selected:
            show_toast(
                self,
                "Replace",
                "No icon selected",
                ToastPreset.WARNING_DARK,
            )
            return

        if not self.service.image_path:
            show_toast(
                self,
                "Replace",
                "Please select an image first",
                ToastPreset.WARNING_DARK,
            )
            return

        try:
            # Create backup if enabled
            if APP_CONFIG.create_backup and not self.selected.has_backup:
                self.service.create_backup(self.selected.name)
                self.model.set_backup_state(self.selected.id, True)

            # Replace the icon
            self.service.replace_bundle()

            # Refresh displays
            self.model.refresh(force_reload=True)
            self._load_current_icon_display()

            show_toast(
                self,
                "Card Icon",
                f'Icon "{self.selected.name}" replacement successful',
                ToastPreset.SUCCESS_DARK,
            )

        except Exception as e:
            show_toast(
                self,
                "Card Icon",
                f"Icon replacement failed: {str(e)}",
                ToastPreset.ERROR_DARK,
            )
