from PySide6 import QtWidgets
from PySide6.QtCore import Qt, QSize, QSettings, QTimer
from PySide6.QtGui import QPixmap, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListView,
    QLayout,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
)
from pyqttoast import ToastPreset

from pages.base_responsive_page import ResponsivePageMixin
from pages.models.field_list_model import FieldListModel
from pages.ui.field import Ui_Field
from services.field_service import FieldService
from unity.unity_utils import fetch_field_thumb
from util.constants import IMAGE_FILTER
from util.ui_util import show_toast
from widgets.ux import configure_editor_chrome, hide_selection_helper, set_button_roles


class Field(ResponsivePageMixin, QtWidgets.QWidget, Ui_Field):
    FIELD_ASPECT_RATIO = 768 / 267
    RESULT_ITEM_SIZE = QSize(150, 72)
    RESULT_ICON_SIZE = QSize(132, 46)
    RESULTS_MIN_HEIGHT = 315

    def __init__(self):
        QtWidgets.QWidget.__init__(self)
        ResponsivePageMixin.__init__(self)
        self.setupUi(self)

        # Configure responsive images with aspect ratio
        self.setup_responsive_images(
            self.current,
            self.preview,
            aspect_ratio=(768, 267),
            max_image_size=900,
        )

        self.service = FieldService()
        self.model = FieldListModel()
        self.fieldsView.setModel(self.model)
        self.selected = None
        self._settings = QSettings("Floowandereeze", "FloowandereezeAndModding")
        configure_editor_chrome(
            self,
            current_widget=self.current,
            preview_widget=self.preview,
            file_edits=(self.assetEdit,),
            list_views=(self.fieldsView,),
            helper_after=self.bundle,
        )
        set_button_roles(self)
        self._configure_split_layout()
        self._set_editor_context("Select a Field")
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
            self.verticalLayout_6,
            self.horizontalLayout_3,
            self.horizontalLayout_4,
        ):
            self.verticalLayout.removeItem(layout)
        self.verticalLayout.removeWidget(self.fieldsView)

        self._configure_editor_controls()

        self.editorPanel = QtWidgets.QWidget(self)
        self.editorPanel.setObjectName("fieldEditorPanel")
        self.editorPanel.setMinimumHeight(230)
        editor_layout = QVBoxLayout(self.editorPanel)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(8)
        editor_layout.addLayout(self.verticalLayout_6)

        self.resultsPanel = QtWidgets.QWidget(self)
        self.resultsPanel.setObjectName("fieldResultsPanel")
        self.resultsPanel.setMinimumHeight(self.RESULTS_MIN_HEIGHT)
        results_layout = QVBoxLayout(self.resultsPanel)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.setSpacing(6)
        results_layout.addLayout(self._build_results_header())
        results_layout.addWidget(self.fieldsView, 1)

        self.fieldSplitter = QSplitter(Qt.Orientation.Vertical, self)
        self.fieldSplitter.setObjectName("fieldSplitter")
        self.fieldSplitter.setChildrenCollapsible(False)
        self.fieldSplitter.setOpaqueResize(True)
        self.fieldSplitter.addWidget(self.editorPanel)
        self.fieldSplitter.addWidget(self.resultsPanel)
        self.fieldSplitter.setStretchFactor(0, 3)
        self.fieldSplitter.setStretchFactor(1, 2)
        self.fieldSplitter.splitterMoved.connect(self._persist_splitter_state)
        self.fieldSplitter.splitterMoved.connect(lambda *_: self._queue_layout_update())

        stored_state = self._settings.value("fields/splitter_state")
        if stored_state:
            self.fieldSplitter.restoreState(stored_state)
        else:
            self.fieldSplitter.setSizes([520, 360])

        self.verticalLayout.addWidget(self.fieldSplitter, 1)

    def _configure_editor_controls(self):
        self.label_4.setText("Image source")
        self.label_4.setStyleSheet("font-weight: 600; color: #ffffff;")
        self.assetEdit.setMinimumWidth(240)
        self.assetEdit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

        for layout, widget in (
            (self.verticalLayout_2, self.label_4),
            (self.verticalLayout_3, self.assetEdit),
            (self.verticalLayout_4, self.selectButton),
            (self.horizontalLayout_4, self.extractButton),
            (self.horizontalLayout_4, self.copyButton),
            (self.horizontalLayout_4, self.replaceButton),
        ):
            layout.removeWidget(widget)

        source_row = QHBoxLayout()
        source_row.setSpacing(8)
        source_row.addWidget(self.label_4)
        source_row.addWidget(self.assetEdit, 1)
        source_row.addWidget(self.selectButton)

        actions_row = QHBoxLayout()
        actions_row.setSpacing(8)
        actions_row.addStretch(1)
        actions_row.addWidget(self.replaceButton)
        actions_row.addWidget(self.extractButton)
        actions_row.addWidget(self.copyButton)
        actions_row.addStretch(1)

        self.verticalLayout_5.setSpacing(6)
        self.verticalLayout_5.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout_5.addLayout(source_row)
        self.verticalLayout_5.addLayout(actions_row)

    def _build_results_header(self):
        self.resultsLabel = QLabel("Results", self)
        self.resultsLabel.setObjectName("resultsLabel")
        self.resultsLabel.setStyleSheet("font-weight: 600; color: #ffffff;")

        results_header = QHBoxLayout()
        results_header.setSpacing(8)
        results_header.setContentsMargins(0, 0, 0, 0)
        results_header.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        results_header.addWidget(self.resultsLabel)
        results_header.addStretch(1)
        return results_header

    def _configure_results_grid(self):
        self.fieldsView.setFlow(QListView.Flow.TopToBottom)
        self.fieldsView.setWrapping(True)
        self.fieldsView.setResizeMode(QListView.ResizeMode.Adjust)
        self.fieldsView.setMovement(QListView.Movement.Static)
        self.fieldsView.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.fieldsView.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.fieldsView.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.fieldsView.setUniformItemSizes(True)
        self.fieldsView.setWordWrap(True)
        self.fieldsView.setIconSize(self.RESULT_ICON_SIZE)
        self.fieldsView.setGridSize(self.RESULT_ITEM_SIZE)
        self.fieldsView.setStyleSheet("""
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
        if not hasattr(self, "fieldsView"):
            return

        self.fieldsView.setIconSize(self.RESULT_ICON_SIZE)
        self.fieldsView.setGridSize(self.RESULT_ITEM_SIZE)
        self.fieldsView.doItemsLayout()

    def _adjust_image_sizes(self):
        if not hasattr(self, "editorPanel"):
            super()._adjust_image_sizes()
            return

        if self.editorPanel.width() <= 0 or self.editorPanel.height() <= 0:
            return

        controls_height = max(72, self.verticalLayout_5.sizeHint().height())
        available_width = max(180, self.editorPanel.width() - 48)
        available_height = max(
            64, (self.editorPanel.height() - controls_height - 56) // 2
        )

        target_width = min(
            self._max_image_size,
            available_width,
            int(available_height * self.FIELD_ASPECT_RATIO),
        )
        target_height = max(64, int(target_width / self.FIELD_ASPECT_RATIO))

        for label in (self.current, self.preview):
            label.setFixedSize(QSize(target_width, target_height))
            label.updateGeometry()

    def _queue_initial_layout_update(self):
        for delay in (0, 50, 150):
            QTimer.singleShot(delay, self._refresh_layout_after_show)

    def _queue_layout_update(self):
        QTimer.singleShot(0, self._refresh_layout_after_show)
        QTimer.singleShot(25, self._refresh_layout_after_show)

    def _refresh_layout_after_show(self):
        self.fieldSplitter.updateGeometry()
        self.editorPanel.updateGeometry()
        self.resultsPanel.updateGeometry()
        self._adjust_image_sizes()
        self._update_results_grid()

    def _persist_splitter_state(self):
        self._settings.setValue("fields/splitter_state", self.fieldSplitter.saveState())

    def _set_editor_context(self, text):
        self.bundle.setText(text)
        self.label.setText(f"Fields · {text}")

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
        self._set_editor_context(f"Editing {self.selected.bundle}")

        self.replaceButton.setEnabled(True)
        self.extractButton.setEnabled(True)
        self.copyButton.setEnabled(True)
        hide_selection_helper(self)

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
