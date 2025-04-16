from os.path import isfile, join

from PIL import Image
from PIL.Image import Resampling
from PySide6 import QtWidgets
from PySide6.QtWidgets import QFileDialog
from pyqttoast import ToastPreset


from pages.ui.background import Ui_Background
from unity.unity_utils import (
    fetch_home_bg,
    extract_unity3d_image,
    replace_unity3d_asset,
)
from util.constants import IMAGE_FILTER, FILE, APP_CONFIG
from util.ui_util import show_toast


class Background(QtWidgets.QWidget, Ui_Background):
    def __init__(self):
        super(Background, self).__init__()
        self.setupUi(self)

        self._connect_callbacks()
        self._load_home_bg()

        self.image_path: str

    def _connect_callbacks(self):
        self.selectButton.clicked.connect(self._select_image)
        self.replaceButton.clicked.connect(self._replace)
        self.extractButton.clicked.connect(self._extract_texture)
        self.restoreButton.clicked.connect(self._restore)

    def _restore(self):
        backup = join("backups", FILE["BACKGROUND"] + ".png")
        if isfile(backup):
            replace_unity3d_asset(
                FILE["BACKGROUND"],
                Image.open(backup).resize((1920, 1080), Resampling.LANCZOS),
            )
            self.current.setPixmap(fetch_home_bg().pixmap(1920, 1080))
            show_toast(
                self,
                "Backup",
                "Background restored successfully",
                ToastPreset.SUCCESS_DARK,
            )
        else:
            show_toast(
                self, "Backup", "Background backup not found", ToastPreset.WARNING_DARK
            )

    def _load_home_bg(self):
        home_bg = fetch_home_bg()
        if home_bg:
            self.current.setPixmap(home_bg.pixmap(1920, 1080))

    def _select_image(self):
        file, _ = QFileDialog.getOpenFileUrl(self, "Select Image", "", IMAGE_FILTER)

        if file and file.url() != "":
            local_file = file.toLocalFile()

            self.assetEdit.setText(local_file)
            self.image_path = local_file

    def _extract_texture(self):
        extract_unity3d_image(FILE["BACKGROUND"])
        show_toast(
            self,
            "Background Extraction",
            'Background extracted to the "images" folder',
            ToastPreset.SUCCESS_DARK,
        )

    def _replace(self):
        if APP_CONFIG.create_backup and not isfile(
            join("backups", FILE["BACKGROUND"] + ".png")
        ):
            extract_unity3d_image(FILE["BACKGROUND"], backup=True)

        replace_unity3d_asset(
            FILE["BACKGROUND"],
            Image.open(self.image_path).resize((1920, 1080), Resampling.LANCZOS),
        )
        self.current.setPixmap(fetch_home_bg().pixmap(1920, 1080))

        show_toast(
            self,
            "Background",
            "Background replacement successful",
            ToastPreset.SUCCESS_DARK,
        )
