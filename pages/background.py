from os.path import isfile, join

from PIL import Image
from PIL.Image import Resampling
from PySide6 import QtCore, QtWidgets
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QFileDialog
from pyqttoast import ToastPreset


from pages.base_responsive_page import ResponsivePageMixin
from pages.ui.background import Ui_Background
from unity.unity_utils import (
    fetch_home_bg,
    extract_unity3d_image,
    replace_unity3d_asset,
)
from util.constants import IMAGE_FILTER, FILE, APP_CONFIG
from util.ui_util import show_toast
from widgets.ux import configure_editor_chrome, set_button_roles
from widgets.image_fit import InlineImageFitController

WIDGET_SIZE_MAX = 16777215


class Background(ResponsivePageMixin, QtWidgets.QWidget, Ui_Background):
    def __init__(self):
        QtWidgets.QWidget.__init__(self)
        ResponsivePageMixin.__init__(self)
        self.setupUi(self)

        # Configure responsive images with aspect ratio
        self.setup_responsive_images(
            self.current, None, aspect_ratio=(1920, 1080)  # No preview label
        )
        configure_editor_chrome(
            self,
            current_widget=self.current,
            current_title="Current",
            file_edits=(self.assetEdit,),
        )
        self._configure_background_preview()
        self.image_fit = InlineImageFitController(
            self,
            self.current,
            (1920, 1080),
            lambda image_path: setattr(self, "image_path", image_path),
        )
        set_button_roles(self)

        # Enable drag and drop
        self.setAcceptDrops(True)

        self._connect_callbacks()
        self._load_home_bg()

        self.image_path: str

    def _configure_background_preview(self) -> None:
        """Allow the background preview to use the full available 16:9 area."""
        self._min_image_size = 128
        self._max_image_size = WIDGET_SIZE_MAX

        self.label.setScaledContents(False)
        self.label.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

        self.current.setScaledContents(True)
        self.current.setMinimumSize(128, 72)
        self.current.setMaximumSize(WIDGET_SIZE_MAX, WIDGET_SIZE_MAX)
        self.current.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self._configure_current_preview_layout()

        for spacer in (self.horizontalSpacer_6, self.horizontalSpacer_5):
            spacer.changeSize(
                0,
                0,
                QtWidgets.QSizePolicy.Policy.Minimum,
                QtWidgets.QSizePolicy.Policy.Minimum,
            )

        self.horizontalLayout.setStretch(0, 0)
        self.horizontalLayout.setStretch(1, 1)
        self.horizontalLayout.setStretch(2, 0)
        self.verticalLayout_5.setStretch(0, 0)
        self.verticalLayout_5.setStretch(1, 0)
        self.verticalLayout_5.setStretch(2, 0)
        self.verticalLayout_5.setStretch(3, 1)
        self.verticalLayout.setStretch(0, 1)
        self.verticalLayout.setStretch(1, 0)
        self.verticalLayout.setAlignment(
            self.verticalLayout_5, QtCore.Qt.AlignmentFlag.AlignTop
        )
        self.verticalSpacer.changeSize(
            0,
            0,
            QtWidgets.QSizePolicy.Policy.Minimum,
            QtWidgets.QSizePolicy.Policy.Minimum,
        )
        self.verticalLayout.invalidate()
        self.verticalLayout_5.invalidate()

        self._queue_background_preview_resize()

    def _configure_current_preview_layout(self) -> None:
        """Keep the preview title compact so the image gets the spare height."""
        current_header = self.findChild(QtWidgets.QLabel, "currentHeaderLabel")
        if current_header is not None:
            current_header.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Preferred,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
            current_header.setMinimumHeight(0)
            current_header.setMaximumHeight(current_header.sizeHint().height())

        preview_layout = self.horizontalLayout.itemAt(1).layout()
        if preview_layout is not None:
            if current_header is not None:
                preview_layout.setAlignment(
                    current_header,
                    QtCore.Qt.AlignmentFlag.AlignHCenter,
                )
            preview_layout.setAlignment(
                self.current,
                QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignTop,
            )

    def resizeEvent(self, event: QtCore.QEvent) -> None:
        """Resize the background preview to the largest available 16:9 size."""
        QtWidgets.QWidget.resizeEvent(self, event)
        self._resize_background_preview()

    def _queue_background_preview_resize(self) -> None:
        """Resize after Qt has settled inserted labels and layout geometry."""
        QtCore.QTimer.singleShot(0, self._resize_background_preview)

    def _resize_background_preview(self) -> None:
        available_width = self.horizontalLayout.geometry().width()
        current_top = self.current.mapTo(self, QtCore.QPoint(0, 0)).y()
        available_height = (
            self.contentsRect().bottom()
            - current_top
            + 1
            - self.image_fit.controls_height()
        )

        if available_width <= 0 or available_height <= 0:
            return

        target_width = available_width
        target_height = round(target_width * 9 / 16)

        if target_height > available_height:
            target_height = available_height
            target_width = round(target_height * 16 / 9)

        target_width = max(1, target_width)
        target_height = max(1, target_height)

        if (
            self.current.size().width() != target_width
            or self.current.size().height() != target_height
        ):
            self.current.setFixedSize(target_width, target_height)

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
            self._queue_background_preview_resize()
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
            self._queue_background_preview_resize()

    def _select_image(self):
        file, _ = QFileDialog.getOpenFileUrl(self, "Select Image", "", IMAGE_FILTER)

        if file and file.url() != "":
            local_file = file.toLocalFile()

            self._set_image(local_file)

    def _set_image(self, file_path: str) -> None:
        if not self.image_fit.set_source(file_path):
            return
        self.assetEdit.setText(file_path)

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
        self._queue_background_preview_resize()

        show_toast(
            self,
            "Background",
            "Background replacement successful",
            ToastPreset.SUCCESS_DARK,
        )
