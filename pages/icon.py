from PySide6 import QtWidgets
from PySide6.QtGui import QPixmap, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QFileDialog
from pyqttoast import ToastPreset

from pages.models.icon_list_model import IconListModel
from pages.ui.icon import Ui_Icon
from services.icon_service import IconService
from unity.unity_utils import fetch_bundle_thumb
from util.constants import IMAGE_FILTER, APP_CONFIG
from util.ui_util import show_toast


class Icon(QtWidgets.QWidget, Ui_Icon):
    def __init__(self):
        super(Icon, self).__init__()
        self.setupUi(self)

        self.service = IconService()
        self.model = IconListModel()
        self.iconsView.setModel(self.model)
        self.selected = None

        # Enable drag and drop
        self.setAcceptDrops(True)

        self._connect_callbacks()

    def _connect_callbacks(self):
        self.iconsView.clicked.connect(self._on_icon_clicked)
        self.selectButton.clicked.connect(self._select_image)
        self.replaceButton.clicked.connect(self._replace)
        self.copyButton.clicked.connect(self._copy)
        self.extractButton.clicked.connect(self._extract_texture)
        self.restoreButton.clicked.connect(self._restore)

    def _restore(self):
        icons = self.service.bundle
        self.service.bundle = self.service.bundle.bundle_big
        if self.service.restore_asset():
            self.model.refresh()
            show_toast(
                self, "Backup", "Card restored successfully", ToastPreset.SUCCESS_DARK
            )
        else:
            show_toast(
                self, "Backup", "Card backup not found", ToastPreset.WARNING_DARK
            )
        self.service.bundle = icons

    def _on_icon_clicked(self, index):
        self.selected = self.model.assets[index.row()]

        self.current.setPixmap(
            fetch_bundle_thumb(self.selected.bundle_medium, (256, 256)).pixmap(256, 256)
        )
        self.service.bundle = self.selected
        self.bundle.setText(
            f"Editing {self.model.assets[index.row()].name} (S: {self.selected.bundle_small} M: {self.selected.bundle_medium} B: {self.selected.bundle_big})"
        )
        self.replaceButton.setEnabled(True)
        self.extractButton.setEnabled(True)
        self.restoreButton.setEnabled(True)
        self.copyButton.setEnabled(True)

    def _copy(self):
        self.service.copy_bundle()
        show_toast(
            self,
            "Icon Copying",
            'Icon copied to the "icons" folder',
            ToastPreset.SUCCESS_DARK,
        )

    def _select_image(self):
        file, _ = QFileDialog.getOpenFileUrl(self, "Select Image", "", IMAGE_FILTER)

        if file and file.url() != "":
            local_file = file.toLocalFile()

            self.assetEdit.setText(local_file)
            self.preview.setPixmap(QPixmap(local_file))
            self.service.image_path = local_file

    def _extract_texture(self):
        icons = self.service.bundle
        for bundle in [
            self.service.bundle.bundle_small,
            self.service.bundle.bundle_medium,
            self.service.bundle.bundle_big,
        ]:
            self.service.bundle = bundle
            self.service.extract_texture(bundle)

        self.service.bundle = icons
        show_toast(
            self,
            "Icon Extraction",
            'Icon extracted to the "icons" folder',
            ToastPreset.SUCCESS_DARK,
        )

    def _replace(self):
        if APP_CONFIG.create_backup and not self.selected.has_backup:
            icons = self.service.bundle
            self.service.bundle = self.service.bundle.bundle_big
            self.service.create_backup(self.service.bundle)
            self.service.bundle = icons
            self.model.set_backup_state(self.selected.id, True)

        self.service.replace_bundle()
        self.model.refresh()
        self.current.setPixmap(
            fetch_bundle_thumb(self.service.bundle.bundle_medium, (256, 256)).pixmap(
                256, 256
            )
        )

        show_toast(
            self, "Icon", "Icon replacement successful", ToastPreset.SUCCESS_DARK
        )

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
