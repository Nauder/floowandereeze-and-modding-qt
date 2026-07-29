from typing import Optional

from PySide6 import QtWidgets
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QFileDialog
from pyqttoast import ToastPreset

from database.models import FaceModel
from pages.base_responsive_page import ResponsivePageMixin
from pages.models.face_list_model import FaceListModel
from pages.ui.face import Ui_Face
from services.face_service import FaceService
from unity.unity_utils import fetch_unity3d_image
from util.constants import IMAGE_FILTER, APP_CONFIG
from util.image_utils import slugify
from util.ui_util import show_toast
from widgets.ux import configure_editor_chrome, hide_selection_helper, set_button_roles
from widgets.image_fit import InlineImageFitController


class Face(ResponsivePageMixin, QtWidgets.QWidget, Ui_Face):
    def __init__(self):
        QtWidgets.QWidget.__init__(self)
        ResponsivePageMixin.__init__(self)
        self.setupUi(self)

        # Configure responsive images with aspect ratio
        self.setup_responsive_images(
            self.current,
            self.preview,
            aspect_ratio=(256, 375),
            max_image_size=250,
            min_image_size=64,
        )

        self.service = FaceService()
        self.model = FaceListModel()
        self.facesView.setModel(self.model)
        self.selected: Optional[FaceModel] = None
        configure_editor_chrome(
            self,
            current_widget=self.current,
            preview_widget=self.preview,
            file_edits=(self.assetEdit,),
            list_views=(self.facesView,),
            helper_after=self.bundle,
        )
        self.image_fit = InlineImageFitController(
            self,
            self.preview,
            (256, 375),
            lambda image_path: setattr(self.service, "image_path", image_path),
            alignment_widget=self.current,
        )
        set_button_roles(self)

        # Enable drag and drop
        self.setAcceptDrops(True)

        self._connect_callbacks()

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
        self.assetEdit.setText(file_path)

    def _connect_callbacks(self) -> None:
        self.facesView.clicked.connect(self._on_face_clicked)
        self.selectButton.clicked.connect(self._select_image)
        self.replaceButton.clicked.connect(self._replace)
        self.extractButton.clicked.connect(self._extract_texture)
        self.restoreButton.clicked.connect(self._restore)

    def _restore(self) -> None:
        if self.service.restore_asset(slugify(self.selected.name)):
            self.model.refresh()
            show_toast(
                self,
                "Backup",
                "Card Face restored successfully",
                ToastPreset.SUCCESS_DARK,
            )
        else:
            show_toast(
                self, "Backup", "Card Face backup not found", ToastPreset.WARNING_DARK
            )

    def _on_face_clicked(self, index) -> None:
        self.selected = self.model.assets[index.row()]

        icon = fetch_unity3d_image(self.selected.key, (256, 375))
        if icon:
            self.current.setPixmap(icon.pixmap(256, 375))
        self.service.key = self.selected.key
        self.bundle.setText(f"Editing {self.selected.name} ({self.selected.key})")

        self.replaceButton.setEnabled(True)
        self.extractButton.setEnabled(True)
        self.restoreButton.setEnabled(True)
        hide_selection_helper(self)

    def _select_image(self) -> None:
        file, _ = QFileDialog.getOpenFileUrl(self, "Select Image", "", IMAGE_FILTER)

        if file and file.url() != "":
            local_file = file.toLocalFile()

            self._set_image(local_file)

    def _extract_texture(self) -> None:
        self.service.extract_texture(self.service.key)
        show_toast(
            self,
            "Face Extraction",
            'Card Face extracted to the "faces" folder',
            ToastPreset.SUCCESS_DARK,
        )

    def _replace(self) -> None:
        if APP_CONFIG.create_backup and not self.selected.has_backup:
            self.service.extract_texture(self.selected.name, backup=True)
            self.model.set_backup_state(self.selected.id, True)

        self.service.replace_bundle()
        self.model.refresh()
        icon = fetch_unity3d_image(self.service.key, (256, 375))
        if icon:
            self.current.setPixmap(icon.pixmap(256, 375))

        show_toast(
            self, "Face", "Card Face replacement successful", ToastPreset.SUCCESS_DARK
        )
