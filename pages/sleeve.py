from PySide6 import QtWidgets, QtCore
from PySide6.QtGui import QPixmap, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QFileDialog
from pyqttoast import ToastPreset

from database.objects import session
from dialogs.simple_dialogs import show_color_dialog
from pages.base_responsive_page import ResponsivePageMixin
from pages.models.sleeve_list_model import SleeveListModel
from pages.ui.sleeve import Ui_Sleeve
from services.sleeve_service import SleeveService
from unity.unity_utils import fetch_bundle_thumb
from util.constants import IMAGE_FILTER, APP_CONFIG
from util.ui_util import show_toast
from widgets.ux import configure_editor_chrome, hide_selection_helper, set_button_roles


class Sleeve(ResponsivePageMixin, QtWidgets.QWidget, Ui_Sleeve):
    def __init__(self):
        QtWidgets.QWidget.__init__(self)
        ResponsivePageMixin.__init__(self)
        self.setupUi(self)

        self._min_image_size = 96
        self._max_image_size = 180

        # Configure responsive images with aspect ratio (portrait card sleeves)
        self.setup_responsive_images(
            self.current, self.preview, aspect_ratio=(256, 374)
        )

        self.service = SleeveService()
        self.model = SleeveListModel()
        self.sleevesView.setModel(self.model)
        self.selected = None
        configure_editor_chrome(
            self,
            current_widget=self.current,
            preview_widget=self.preview,
            file_edits=(self.sleeveEdit,),
            list_views=(self.sleevesView,),
            helper_after=self.bundle,
        )
        set_button_roles(self)

        # Enable drag and drop
        self.setAcceptDrops(True)

        self._connect_callbacks()

    def resizeEvent(self, event: QtCore.QEvent):
        super().resizeEvent(event)
        self._adjust_list_view_icons(self.sleevesView, 128, 181)

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
                self.sleeveEdit.setText(file_path)
                self.preview.setPixmap(QPixmap(file_path))
                self.service.image_path = file_path
                break

    def _restore(self):
        if self.service.restore_asset():
            self.model.refresh()
            show_toast(
                self, "Backup", "Sleeve restored successfully", ToastPreset.SUCCESS_DARK
            )
        else:
            show_toast(
                self, "Backup", "Sleeve backup not found", ToastPreset.WARNING_DARK
            )

    def _connect_callbacks(self):
        self.sleevesView.clicked.connect(self._on_sleeve_clicked)
        self.selectButton.clicked.connect(self._select_image)
        self.replaceButton.clicked.connect(self._replace_sleeve)
        self.copyButton.clicked.connect(self._copy)
        self.extractButton.clicked.connect(self._extract_texture)
        self.borderButton.clicked.connect(self._select_color)
        self.restoreButton.clicked.connect(self._restore)
        self.checkBox.clicked.connect(self._switch_border)
        self.fadeCheckBox.clicked.connect(self._toggle_fade)
        self.favoriteBox.stateChanged.connect(self._toggle_favorite)
        self.favoritesBox.stateChanged.connect(self._toggle_favorites_filter)

    def _toggle_favorite(self, state):
        if self.selected and self.selected.favorite != (
            state == QtCore.Qt.CheckState.Checked.value
        ):
            self.selected.favorite = state == QtCore.Qt.CheckState.Checked.value
            session.commit()
            show_toast(
                self,
                "Favorite",
                "Sleeve favorite status updated",
                ToastPreset.SUCCESS_DARK,
            )

    def _toggle_favorites_filter(self, state):
        self.model.show_favorites = state == QtCore.Qt.CheckState.Checked.value
        if self.model.show_favorites:
            self.model.refresh()
            self.model.layoutChanged.emit()
        else:
            self.model.refresh()
            self.model.layoutChanged.emit()

    def _on_sleeve_clicked(self, index):
        self.selected = self.model.assets[index.row()]

        self.current.setPixmap(
            fetch_bundle_thumb(self.selected.bundle, (256, 375)).pixmap(256, 375)
        )
        self.service.bundle = self.selected.bundle
        self.bundle.setText(f"Editing {self.selected.bundle}")

        self.replaceButton.setEnabled(True)
        self.extractButton.setEnabled(True)
        self.restoreButton.setEnabled(True)
        self.copyButton.setEnabled(True)
        self.favoriteBox.setChecked(self.selected.favorite)
        hide_selection_helper(self)

    def _select_image(self):
        file, _ = QFileDialog.getOpenFileUrl(self, "Select Image", "", IMAGE_FILTER)

        if file and file.url() != "":
            local_file = file.toLocalFile()

            self.sleeveEdit.setText(local_file)
            self.preview.setPixmap(QPixmap(local_file))
            self.service.image_path = local_file

    def _copy(self):
        self.service.copy_bundle()
        show_toast(
            self,
            "Sleeve Copying",
            'Sleeve copied to the "sleeves" folder',
            ToastPreset.SUCCESS_DARK,
        )

    def _extract_texture(self):
        self.service.extract_texture(self.service.bundle)
        show_toast(
            self,
            "Sleeve Extraction",
            'Sleeve extracted to the "sleeves" folder',
            ToastPreset.SUCCESS_DARK,
        )

    def _replace_sleeve(self):
        if APP_CONFIG.create_backup and not self.selected.has_backup:
            self.service.create_backup(self.service.bundle)
            self.model.set_backup_state(self.selected.id, True)

        self.service.replace_bundle()
        self.model.refresh()
        self.current.setPixmap(
            fetch_bundle_thumb(self.service.bundle, (256, 375)).pixmap(256, 375)
        )

        show_toast(
            self, "Sleeve", "Sleeve replacement successful", ToastPreset.SUCCESS_DARK
        )

    def _select_color(self):
        color = show_color_dialog()

        if color:
            self.service.border_color = color.name()
            self.borderEdit.setText(color.name())
            self._switch_border()

    def _switch_border(self):
        border_enabled = self.checkBox.isChecked()
        self.fadeCheckBox.setEnabled(border_enabled)

        if border_enabled:
            # For preview, we'll use a simple border - the actual fade effect will be applied during replacement
            self.preview.setStyleSheet(f"""
                #preview {{
                    border: 15px solid {self.service.border_color};
                }}
            """)
        else:
            self.preview.setStyleSheet("")
            self.fadeCheckBox.setChecked(False)

        self.service.border = border_enabled
        self.service.border_fade = self.fadeCheckBox.isChecked()

    def _toggle_fade(self):
        self.service.border_fade = self.fadeCheckBox.isChecked()
        # Update preview to show fade effect indication (we'll keep the simple border for preview)
        if self.fadeCheckBox.isChecked() and self.checkBox.isChecked():
            # Could add a visual indicator that fade is enabled, but for now keep simple border
            pass
