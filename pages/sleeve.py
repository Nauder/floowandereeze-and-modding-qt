from PySide6 import QtWidgets
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFileDialog
from pyqttoast import ToastPreset

from dialogs.simple_dialogs import show_color_dialog
from pages.models.sleeve_list_model import SleeveListModel
from pages.ui.sleeve import Ui_Sleeve
from services.sleeve_service import SleeveService
from unity.unity_utils import fetch_bundle_thumb
from util.constants import IMAGE_FILTER, APP_CONFIG
from util.ui_util import show_toast


class Sleeve(QtWidgets.QWidget, Ui_Sleeve):
    def __init__(self):
        super(Sleeve, self).__init__()
        self.setupUi(self)

        self.service = SleeveService()
        self.model = SleeveListModel()
        self.sleevesView.setModel(self.model)
        self.selected = None

        self._connect_callbacks()

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
        if self.checkBox.isChecked():
            self.preview.setStyleSheet(
                f"""
                #preview {{
                    border: 15px solid {self.service.border_color};
                }}
            """
            )
        else:
            self.preview.setStyleSheet("")

        self.service.border = self.checkBox.isChecked()
