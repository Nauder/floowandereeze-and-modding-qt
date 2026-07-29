from PySide6 import QtWidgets
from PySide6.QtCore import Qt, QSize, QSettings, QTimer
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListView,
    QLayout,
    QSizePolicy,
    QVBoxLayout,
)
from pyqttoast import ToastPreset

from database.objects import session
from widgets.grip_splitter import GripSplitter
from pages.base_responsive_page import ResponsivePageMixin
from pages.models.icon_list_model import IconListModel
from pages.ui.icon import Ui_Icon
from services.icon_service import IconService
from unity.unity_utils import fetch_bundle_thumb
from util.constants import IMAGE_FILTER, APP_CONFIG
from util.ui_util import show_toast
from widgets.ux import configure_editor_chrome, hide_selection_helper, set_button_roles
from widgets.image_fit import InlineImageFitController


class Icon(ResponsivePageMixin, QtWidgets.QWidget, Ui_Icon):
    RESULT_ITEM_SIZE = QSize(116, 132)
    RESULT_ICON_SIZE = QSize(96, 96)
    RESULTS_MIN_HEIGHT = 315

    def __init__(self):
        QtWidgets.QWidget.__init__(self)
        ResponsivePageMixin.__init__(self)
        self.setupUi(self)

        # Configure responsive images with aspect ratio
        self.setup_responsive_images(
            self.current,
            self.preview,
            aspect_ratio=(256, 256),
            max_image_size=500,
            min_image_size=64,
        )

        self.service = IconService()
        self.model = IconListModel()
        self.iconsView.setModel(self.model)
        self.selected = None
        self._settings = QSettings("Floowandereeze", "FloowandereezeAndModding")
        configure_editor_chrome(
            self,
            current_widget=self.current,
            preview_widget=self.preview,
            file_edits=(self.assetEdit,),
            list_views=(self.iconsView,),
            helper_after=self.bundle,
        )
        self.image_fit = InlineImageFitController(
            self,
            self.preview,
            (512, 512),
            lambda image_path: setattr(self.service, "image_path", image_path),
            alignment_widget=self.current,
        )
        set_button_roles(self)
        self._configure_split_layout()
        self._set_editor_context("Select an Icon")
        self._configure_results_grid()
        self._queue_initial_layout_update()

        # Enable drag and drop
        self.setAcceptDrops(True)

        self._connect_callbacks()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_results_grid()

    def showEvent(self, event):
        super().showEvent(event)
        self._queue_initial_layout_update()

    def _configure_split_layout(self):
        self.verticalLayout.setSpacing(8)
        self.verticalLayout.setContentsMargins(12, 8, 12, 12)
        self.label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.label.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.bundle.hide()

        for layout in (
            self.main_content,
            self.horizontalLayout_3,
            self.horizontalLayout_4,
            self.favoritesLayout,
        ):
            self.verticalLayout.removeItem(layout)
        self.verticalLayout.removeWidget(self.iconsView)

        self._configure_editor_controls()

        self.editorPanel = QtWidgets.QWidget(self)
        self.editorPanel.setObjectName("iconEditorPanel")
        self.editorPanel.setMinimumHeight(230)
        editor_layout = QVBoxLayout(self.editorPanel)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(8)
        editor_layout.addLayout(self.main_content)

        self.resultsPanel = QtWidgets.QWidget(self)
        self.resultsPanel.setObjectName("iconResultsPanel")
        self.resultsPanel.setMinimumHeight(self.RESULTS_MIN_HEIGHT)
        results_layout = QVBoxLayout(self.resultsPanel)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.setSpacing(6)
        results_layout.addLayout(self._build_results_header())
        results_layout.addWidget(self.iconsView, 1)

        self.iconSplitter = GripSplitter(Qt.Orientation.Vertical, self)
        self.iconSplitter.setObjectName("iconSplitter")
        self.iconSplitter.setChildrenCollapsible(False)
        self.iconSplitter.setOpaqueResize(True)
        self.iconSplitter.addWidget(self.editorPanel)
        self.iconSplitter.addWidget(self.resultsPanel)
        self.iconSplitter.setStretchFactor(0, 3)
        self.iconSplitter.setStretchFactor(1, 2)
        self.iconSplitter.splitterMoved.connect(self._persist_splitter_state)
        self.iconSplitter.splitterMoved.connect(lambda *_: self._queue_layout_update())

        stored_state = self._settings.value("icons/splitter_state")
        if stored_state:
            self.iconSplitter.restoreState(stored_state)
        else:
            self.iconSplitter.setSizes([520, 360])

        self.verticalLayout.addWidget(self.iconSplitter, 1)

    def _configure_editor_controls(self):
        self.label_4.setText("Image source")
        self.label_4.setStyleSheet("font-weight: 600; color: #ffffff;")
        self.assetEdit.setMinimumWidth(210)
        self.assetEdit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

        for layout, widget in (
            (self.verticalLayout_2, self.label_4),
            (self.verticalLayout_3, self.assetEdit),
            (self.verticalLayout_4, self.selectButton),
            (self.horizontalLayout_4, self.restoreButton),
            (self.horizontalLayout_4, self.extractButton),
            (self.horizontalLayout_4, self.copyButton),
            (self.horizontalLayout_4, self.replaceButton),
            (self.favoritesLayout, self.favoriteBox),
        ):
            layout.removeWidget(widget)

        self.verticalLayout_5.setSpacing(8)
        self.verticalLayout_5.setContentsMargins(0, 26, 0, 0)
        self.verticalLayout_5.addStretch(1)
        self.verticalLayout_5.addWidget(self.label_4)
        self.verticalLayout_5.addWidget(self.assetEdit)
        self.verticalLayout_5.addWidget(self.selectButton)
        self.verticalLayout_5.addSpacing(6)
        self.verticalLayout_5.addWidget(
            self.replaceButton, alignment=Qt.AlignmentFlag.AlignHCenter
        )
        self.verticalLayout_5.addWidget(self.restoreButton)

        secondary_actions = QHBoxLayout()
        secondary_actions.setSpacing(6)
        secondary_actions.addWidget(self.extractButton)
        secondary_actions.addWidget(self.copyButton)
        self.verticalLayout_5.addLayout(secondary_actions)

        self.verticalLayout_5.addWidget(self.favoriteBox)
        self.verticalLayout_5.addStretch(1)

    def _build_results_header(self):
        self.resultsLabel = QLabel("Results", self)
        self.resultsLabel.setObjectName("resultsLabel")
        self.resultsLabel.setStyleSheet("font-weight: 600; color: #ffffff;")

        self.favoritesLayout.removeItem(self.horizontalSpacer_9)
        self.favoritesLayout.removeItem(self.horizontalSpacer_10)
        self.favoritesLayout.removeItem(self.horizontalSpacer_11)
        self.favoritesLayout.insertWidget(0, self.resultsLabel)
        self.favoritesLayout.setSpacing(8)
        self.favoritesLayout.setContentsMargins(0, 0, 0, 0)
        self.favoritesLayout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        return self.favoritesLayout

    def _configure_results_grid(self):
        self.iconsView.setFlow(QListView.Flow.TopToBottom)
        self.iconsView.setWrapping(True)
        self.iconsView.setResizeMode(QListView.ResizeMode.Adjust)
        self.iconsView.setMovement(QListView.Movement.Static)
        self.iconsView.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.iconsView.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.iconsView.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.iconsView.setUniformItemSizes(True)
        self.iconsView.setWordWrap(True)
        self.iconsView.setIconSize(self.RESULT_ICON_SIZE)
        self.iconsView.setGridSize(self.RESULT_ITEM_SIZE)
        self.iconsView.setStyleSheet("""
            QListView::item {
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 4px;
            }
            QListView::item:selected {
                background: rgba(21, 160, 111, 0.24);
                border: 2px solid #15a06f;
            }
            QListView::item:focus {
                border: 2px solid #15a06f;
            }
            """)
        self._update_results_grid()

    def _update_results_grid(self):
        if not hasattr(self, "iconsView"):
            return

        self.iconsView.setIconSize(self.RESULT_ICON_SIZE)
        self.iconsView.setGridSize(self.RESULT_ITEM_SIZE)
        self.iconsView.doItemsLayout()

    def _adjust_image_sizes(self):
        if not hasattr(self, "editorPanel"):
            super()._adjust_image_sizes()
            return

        if self.editorPanel.width() <= 0 or self.editorPanel.height() <= 0:
            return

        available_height = max(
            64, self.editorPanel.height() - 34 - self.image_fit.controls_height()
        )
        available_width = max(64, self.editorPanel.width() // 3)
        target_size = max(
            64,
            min(self._max_image_size, available_height, available_width),
        )

        for label in (self.current, self.preview):
            label.setFixedSize(QSize(target_size, target_size))
            label.updateGeometry()

    def _queue_initial_layout_update(self):
        for delay in (0, 50, 150):
            QTimer.singleShot(delay, self._refresh_layout_after_show)

    def _queue_layout_update(self):
        QTimer.singleShot(0, self._refresh_layout_after_show)
        QTimer.singleShot(25, self._refresh_layout_after_show)

    def _refresh_layout_after_show(self):
        self.iconSplitter.updateGeometry()
        self.editorPanel.updateGeometry()
        self.resultsPanel.updateGeometry()
        self._adjust_image_sizes()
        self._update_results_grid()

    def _persist_splitter_state(self):
        self._settings.setValue("icons/splitter_state", self.iconSplitter.saveState())

    def _set_editor_context(self, text):
        self.bundle.setText(text)
        self.label.setText(f"Icons · {text}")

    def _connect_callbacks(self):
        self.iconsView.clicked.connect(self._on_icon_clicked)
        self.selectButton.clicked.connect(self._select_image)
        self.replaceButton.clicked.connect(self._replace)
        self.copyButton.clicked.connect(self._copy)
        self.extractButton.clicked.connect(self._extract_texture)
        self.restoreButton.clicked.connect(self._restore)
        self.favoriteBox.stateChanged.connect(self._toggle_favorite)
        self.favoritesBox.stateChanged.connect(self._toggle_favorites_filter)

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
        self._set_editor_context(
            f"Editing {self.model.assets[index.row()].name} (S: {self.selected.bundle_small} M: {self.selected.bundle_medium} B: {self.selected.bundle_big})"
        )
        self.replaceButton.setEnabled(True)
        self.extractButton.setEnabled(True)
        self.restoreButton.setEnabled(True)
        self.copyButton.setEnabled(True)
        self.favoriteBox.setEnabled(True)
        self.favoriteBox.setChecked(self.selected.favorite)
        hide_selection_helper(self)

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

            self._set_image(local_file)

    def _set_image(self, file_path: str) -> None:
        if not self.image_fit.set_source(file_path):
            return
        self.assetEdit.setText(file_path)

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

    def _toggle_favorite(self, state):
        if self.selected and self.selected.favorite != (
            state == Qt.CheckState.Checked.value
        ):
            self.selected.favorite = state == Qt.CheckState.Checked.value
            session.commit()
            show_toast(
                self,
                "Favorite",
                "Icon favorite status updated",
                ToastPreset.SUCCESS_DARK,
            )

    def _toggle_favorites_filter(self, state):
        self.model.show_favorites = state == Qt.CheckState.Checked.value
        if self.model.show_favorites:
            self.model.refresh()
            self.model.layoutChanged.emit()
        else:
            self.model.refresh()
            self.model.layoutChanged.emit()

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
