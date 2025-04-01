from PySide6 import QtWidgets
from PySide6.QtCore import QSize
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import QFileDialog
from pyqttoast import ToastPreset

from pages.models.wallpaper_list_model import WallpaperListModel
from pages.ui.wallpaper import Ui_Wallpaper
from services.wallpaper_service import WallpaperService
from unity.unity_utils import fetch_bundle_thumb
from util.constants import IMAGE_FILTER, APP_CONFIG
from util.ui_util import show_toast
from widgets.image_viewer import ImageViewer


class Wallpaper(QtWidgets.QWidget, Ui_Wallpaper):
    def __init__(self):
        super(Wallpaper, self).__init__()
        self.setupUi(self)

        self.service = WallpaperService()
        self.model = WallpaperListModel()
        self.wallpaperView.setModel(self.model)
        self.selected = None
        self.image = None
        self.preview = ImageViewer(
            QPixmap.fromImage(QImage(":ui/images/wallpaper_preview.png"))
        )
        self.main_content.addWidget(self.preview)

        self._connect_callbacks()

    def _restore(self):
        if self.service.restore_asset():
            self.model.refresh()
            show_toast(
                self,
                "Backup",
                "Wallpaper restored successfully",
                ToastPreset.SUCCESS_DARK,
            )
        else:
            show_toast(
                self, "Backup", "Wallpaper backup not found", ToastPreset.WARNING_DARK
            )

    def _connect_callbacks(self):
        self.wallpaperView.clicked.connect(self._on_wallpaper_clicked)
        self.selectButton.clicked.connect(self._select_image)
        self.replaceButton.clicked.connect(self._replace_wallpaper)
        self.copyButton.clicked.connect(self._copy)
        self.extractButton.clicked.connect(self._extract_texture)
        self.restoreButton.clicked.connect(self._restore)

    def _on_wallpaper_clicked(self, index):
        self.selected = self.model.assets[index.row()]
        self.image = fetch_bundle_thumb(self.selected.bundle_foreground, None)
        size = self.image.availableSizes()[0]
        self.preview.setPixmap(
            self.image.pixmap(self.image.actualSize(QSize(600, 900)))
        )
        self.service.bundle = self.selected
        self.bundle.setText(
            f"Editing {self.selected.name} (F: {self.selected.bundle_foreground} B: {self.selected.bundle_background}) |"
            f" Size: {size.width()}x{size.height()}px"
        )

        self.replaceButton.setEnabled(True)
        self.extractButton.setEnabled(True)
        self.restoreButton.setEnabled(True)
        self.copyButton.setEnabled(True)

    def _select_image(self):
        file, _ = QFileDialog.getOpenFileUrl(self, "Select Image", "", IMAGE_FILTER)

        if file and file.url() != "":
            local_file = file.toLocalFile()

            self.wallpaperEdit.setText(local_file)
            self.service.image_path = local_file

    def _copy(self):
        self.service.copy_bundle()
        show_toast(
            self,
            "Wallpaper Copying",
            'Wallpaper copied to the "wallpapers" folder',
            ToastPreset.SUCCESS_DARK,
        )

    def _extract_texture(self):
        wallpapers = self.service.bundle

        for wallpaper in [
            self.selected.bundle_foreground,
            self.selected.bundle_background,
        ]:
            self.service.bundle = wallpaper
            self.service.extract_texture(self.service.bundle)

        self.service.bundle = wallpapers
        show_toast(
            self,
            "Wallpaper Extraction",
            'Wallpaper extracted to the "wallpapers" folder',
            ToastPreset.SUCCESS_DARK,
        )

    def _replace_wallpaper(self):
        if APP_CONFIG.create_backup and not self.selected.has_backup:
            self.service.create_backup(self.service.bundle)
            self.model.set_backup_state(self.selected.id, True)

        self.service.replace_bundle()
        self.model.refresh()

        show_toast(
            self,
            "Wallpaper",
            "Wallpaper replacement successful",
            ToastPreset.SUCCESS_DARK,
        )
