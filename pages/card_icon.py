"""Card Icon Page Module.

This module provides the card icon modding page for the application.
It allows users to modify card icons from the sprite atlas.
"""

from io import BytesIO
from typing import Optional

from PIL import Image
from PySide6 import QtCore, QtWidgets
from PySide6.QtGui import QPixmap, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QFileDialog
from pyqttoast import ToastPreset

from database.models import CardIconModel
from pages.base_responsive_page import ResponsivePageMixin
from pages.models.card_icon_list_model import CardIconListModel
from pages.ui.card_icon import Ui_CardIcon
from services.card_icon_service import CardIconService
from util.constants import IMAGE_FILTER, APP_CONFIG
from util.ui_util import show_toast


class CardIcon(ResponsivePageMixin, QtWidgets.QWidget, Ui_CardIcon):
    """
    Card icon modding page.

    This page allows users to modify card icons from the sprite atlas.
    It provides functionality to select, preview, replace, extract, and restore card icons.
    """

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
        self.iconsList.setGridSize(QtCore.QSize(112, 96))
        self.iconsList.setTextElideMode(QtCore.Qt.TextElideMode.ElideRight)
        self.iconsList.setUniformItemSizes(True)
        self.iconsList.setWordWrap(False)
        self.selected: Optional[CardIconModel] = None

        # Enable drag and drop
        self.setAcceptDrops(True)

        self._connect_callbacks()

    def resizeEvent(self, event: QtCore.QEvent) -> None:
        """Keep icon previews square while the list consumes spare height."""
        super().resizeEvent(event)
        self._adjust_preview_sizes()

    def _adjust_preview_sizes(self) -> None:
        """Clamp preview labels to a square size so scaled images never stretch."""
        side = max(128, min(self.width() // 4, self.height() // 3, 250))
        for label in (self.current, self.preview):
            label.setFixedSize(side, side)

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
                self.iconEdit.setText(file_path)
                self._update_preview(file_path)
                self.service.image_path = file_path
                self._check_replace_button()
                break

    def _update_preview(self, image_path: str) -> None:
        """Update the preview with the selected image."""
        try:
            # Load and resize image for preview
            img = Image.open(image_path).convert("RGBA")
            img = img.resize((128, 128), Image.Resampling.LANCZOS)

            # Convert to QPixmap
            img_bytes = BytesIO()
            img.save(img_bytes, format="PNG")
            img_bytes.seek(0)
            pixmap = QPixmap()
            pixmap.loadFromData(img_bytes.getvalue())

            self.preview.setPixmap(pixmap)
        except Exception as e:
            print(f"Error updating preview: {e}")

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

        # Update UI
        self.bundle.setText(f"Editing: {self.selected.name}")

        # Load current icon display
        self._load_current_icon_display()

        # Enable buttons
        self.extractButton.setEnabled(True)
        self.restoreButton.setEnabled(True)
        self._check_replace_button()

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
            self.iconEdit.setText(local_file)
            self._update_preview(local_file)
            self.service.image_path = local_file
            self._check_replace_button()

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
