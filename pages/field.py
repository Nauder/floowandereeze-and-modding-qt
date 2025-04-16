from PySide6 import QtWidgets
from PySide6.QtGui import QPixmap, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QFileDialog
from pyqttoast import ToastPreset

from pages.models.field_list_model import FieldListModel
from pages.ui.field import Ui_Field
from services.field_service import FieldService
from unity.unity_utils import fetch_field_thumb
from util.constants import IMAGE_FILTER
from util.ui_util import show_toast


class Field(QtWidgets.QWidget, Ui_Field):
    def __init__(self):
        super(Field, self).__init__()
        self.setupUi(self)

        self.service = FieldService()
        self.model = FieldListModel()
        self.fieldsView.setModel(self.model)
        self.selected = None

        # Enable drag and drop
        self.setAcceptDrops(True)

        self._connect_callbacks()

    def _connect_callbacks(self):
        self.fieldsView.clicked.connect(self._on_field_clicked)
        self.selectButton.clicked.connect(self._select_image)
        self.replaceButton.clicked.connect(self._replace)
        self.extractButton.clicked.connect(self._extract_texture)
        self.copyButton.clicked.connect(self._copy)

    def _on_field_clicked(self, index):
        self.selected = self.model.fields[index.row()]

        self.current.setPixmap(fetch_field_thumb(self.selected).pixmap(768, 267))
        self.service.bundle = self.selected.bundle
        self.bundle.setText(f"Editing {self.selected.bundle}")

        self.replaceButton.setEnabled(True)
        self.extractButton.setEnabled(True)
        self.copyButton.setEnabled(True)

    def _select_image(self):
        file, _ = QFileDialog.getOpenFileUrl(self, "Select Image", "", IMAGE_FILTER)

        if file and file.url() != "":
            local_file = file.toLocalFile()

            self.assetEdit.setText(local_file)
            self.preview.setPixmap(QPixmap(local_file))
            self.service.image_path = local_file

    def _extract_texture(self):
        self.service.extract_texture(self.service.bundle, field=True)
        show_toast(
            self,
            "Field Extraction",
            'Field extracted to the "fields" folder',
            ToastPreset.SUCCESS_DARK,
        )

    def _copy(self):
        self.service.copy_bundle()
        show_toast(
            self,
            "Field Copying",
            'Field copied to the "fields" folder',
            ToastPreset.SUCCESS_DARK,
        )

    def _replace(self):
        self.service.replace_bundle()
        self.model.refresh()
        self.current.setPixmap(fetch_field_thumb(self.selected).pixmap(768, 267))

        show_toast(
            self, "Field", "Field replacement successful", ToastPreset.SUCCESS_DARK
        )

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Accepts drag and drop of image files."""
        if event.mimeData().hasUrls():
            # Check if the dragged file is an image
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        """Handles the drop event of an image file."""
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
                self.assetEdit.setText(file_path)
                self.preview.setPixmap(QPixmap(file_path))
                self.service.image_path = file_path
                break
