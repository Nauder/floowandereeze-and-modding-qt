from typing import Optional

from PySide6 import QtWidgets
from PySide6.QtGui import QPixmap, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QFileDialog
from pyqttoast import ToastPreset

from database.models import FaceModel
from pages.models.face_list_model import FaceListModel
from pages.ui.face import Ui_Face
from services.face_service import FaceService
from unity.unity_utils import fetch_unity3d_image
from util.constants import IMAGE_FILTER, APP_CONFIG
from util.image_utils import slugify
from util.ui_util import show_toast


class Face(QtWidgets.QWidget, Ui_Face):
    def __init__(self):
        super(Face, self).__init__()
        self.setupUi(self)

        self.service = FaceService()
        self.model = FaceListModel()
        self.facesView.setModel(self.model)
        self.selected: Optional[FaceModel] = None

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
                self.assetEdit.setText(file_path)
                self.preview.setPixmap(QPixmap(file_path))
                self.service.image_path = file_path
                break

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

        self.current.setPixmap(
            fetch_unity3d_image(self.selected.key, (256, 375)).pixmap(256, 375)
        )
        self.service.bundle = self.selected.key
        self.bundle.setText(f"Editing {self.selected.name} ({self.selected.key})")

        self.replaceButton.setEnabled(True)
        self.extractButton.setEnabled(True)
        self.restoreButton.setEnabled(True)

    def _select_image(self) -> None:
        file, _ = QFileDialog.getOpenFileUrl(self, "Select Image", "", IMAGE_FILTER)

        if file and file.url() != "":
            local_file = file.toLocalFile()

            self.assetEdit.setText(local_file)
            self.preview.setPixmap(QPixmap(local_file))
            self.service.image_path = local_file

    def _extract_texture(self) -> None:
        self.service.extract_texture(self.service.bundle)
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
        self.current.setPixmap(
            fetch_unity3d_image(self.service.bundle, (256, 375)).pixmap(256, 375)
        )

        show_toast(
            self, "Face", "Card Face replacement successful", ToastPreset.SUCCESS_DARK
        )
