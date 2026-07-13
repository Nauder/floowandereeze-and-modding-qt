from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import QSize, QSettings
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

from database.objects import session
from dialogs.simple_dialogs import show_color_dialog
from pages.base_responsive_page import ResponsivePageMixin
from pages.models.sleeve_list_model import SleeveListModel
from pages.ui.sleeve import Ui_Sleeve
from services.sleeve_service import SleeveService
from unity.unity_utils import fetch_bundle_thumb
from util.constants import IMAGE_FILTER, APP_CONFIG
from util.ui_util import show_toast
from widgets.ux import configure_editor_chrome, hide_selection_helper, set_button_roles


class Sleeve(ResponsivePageMixin, QtWidgets.QWidget, Ui_Sleeve):
    RESULT_ITEM_SIZE = QSize(104, 148)
    RESULT_ICON_SIZE = QSize(90, 132)
    RESULTS_MIN_HEIGHT = 315
    SLEEVE_ASPECT_RATIO = 256 / 374

    def __init__(self):
        QtWidgets.QWidget.__init__(self)
        ResponsivePageMixin.__init__(self)
        self.setupUi(self)

        self._min_image_size = 96
        self._max_image_size = 500

        # Configure responsive images with aspect ratio (portrait card sleeves)
        self.setup_responsive_images(
            self.current, self.preview, aspect_ratio=(256, 374)
        )

        self.service = SleeveService()
        self.model = SleeveListModel()
        self.sleevesView.setModel(self.model)
        self.selected = None
        self._settings = QSettings("Floowandereeze", "FloowandereezeAndModding")
        configure_editor_chrome(
            self,
            current_widget=self.current,
            preview_widget=self.preview,
            file_edits=(self.sleeveEdit,),
            list_views=(self.sleevesView,),
            helper_after=self.bundle,
        )
        set_button_roles(self)
        self._configure_split_layout()
        self._set_editor_context("Select a Sleeve")
        self._configure_results_grid()
        self._queue_initial_layout_update()

        # Enable drag and drop
        self.setAcceptDrops(True)

        self._connect_callbacks()

    def resizeEvent(self, event: QtCore.QEvent):
        super().resizeEvent(event)
        self._update_results_grid()

    def showEvent(self, event: QtCore.QEvent):
        super().showEvent(event)
        self._queue_initial_layout_update()

    def _configure_split_layout(self):
        self.verticalLayout.setSpacing(8)
        self.verticalLayout.setContentsMargins(12, 8, 12, 12)
        self.label.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        self.label.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.bundle.hide()

        for layout in (
            self.main_content,
            self.horizontalLayout_3,
            self.horizontalLayout_4,
            self.horizontalLayout,
        ):
            self.verticalLayout.removeItem(layout)
        self.verticalLayout.removeWidget(self.sleevesView)

        self._configure_editor_controls()

        self.editorPanel = QtWidgets.QWidget(self)
        self.editorPanel.setObjectName("sleeveEditorPanel")
        self.editorPanel.setMinimumHeight(230)
        editor_layout = QVBoxLayout(self.editorPanel)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(8)
        editor_layout.addLayout(self.main_content)

        self.resultsPanel = QtWidgets.QWidget(self)
        self.resultsPanel.setObjectName("sleeveResultsPanel")
        self.resultsPanel.setMinimumHeight(self.RESULTS_MIN_HEIGHT)
        results_layout = QVBoxLayout(self.resultsPanel)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.setSpacing(6)
        results_layout.addLayout(self._build_results_header())
        results_layout.addWidget(self.sleevesView, 1)

        self.sleeveSplitter = QSplitter(QtCore.Qt.Orientation.Vertical, self)
        self.sleeveSplitter.setObjectName("sleeveSplitter")
        self.sleeveSplitter.setChildrenCollapsible(False)
        self.sleeveSplitter.setOpaqueResize(True)
        self.sleeveSplitter.addWidget(self.editorPanel)
        self.sleeveSplitter.addWidget(self.resultsPanel)
        self.sleeveSplitter.setStretchFactor(0, 3)
        self.sleeveSplitter.setStretchFactor(1, 2)
        self.sleeveSplitter.splitterMoved.connect(self._persist_splitter_state)
        self.sleeveSplitter.splitterMoved.connect(
            lambda *_: self._queue_layout_update()
        )

        stored_state = self._settings.value("sleeves/splitter_state")
        if stored_state:
            self.sleeveSplitter.restoreState(stored_state)
        else:
            self.sleeveSplitter.setSizes([520, 360])

        self.verticalLayout.addWidget(self.sleeveSplitter, 1)

    def _configure_editor_controls(self):
        self.label_4.setText("Image source")
        self.label_5.setText("Border color")
        for label in (self.label_4, self.label_5):
            label.setStyleSheet("font-weight: 600; color: #ffffff;")

        for edit in (self.sleeveEdit, self.borderEdit):
            edit.setMinimumWidth(210)
            edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        for layout, widget in (
            (self.verticalLayout_2, self.label_4),
            (self.verticalLayout_2, self.label_5),
            (self.verticalLayout_3, self.sleeveEdit),
            (self.verticalLayout_3, self.borderEdit),
            (self.verticalLayout_4, self.selectButton),
            (self.verticalLayout_4, self.borderButton),
            (self.horizontalLayout_4, self.checkBox),
            (self.horizontalLayout_4, self.fadeCheckBox),
            (self.horizontalLayout_4, self.restoreButton),
            (self.horizontalLayout_4, self.extractButton),
            (self.horizontalLayout_4, self.copyButton),
            (self.horizontalLayout_4, self.replaceButton),
            (self.horizontalLayout_4, self.favoriteBox),
        ):
            layout.removeWidget(widget)

        self.verticalLayout_5.setSpacing(8)
        self.verticalLayout_5.setContentsMargins(0, 18, 0, 0)
        self.verticalLayout_5.addStretch(1)
        self.verticalLayout_5.addWidget(self.label_4)
        self.verticalLayout_5.addWidget(self.sleeveEdit)
        self.verticalLayout_5.addWidget(self.selectButton)
        self.verticalLayout_5.addWidget(self.label_5)

        border_actions = QHBoxLayout()
        border_actions.setSpacing(6)
        border_actions.addWidget(self.borderEdit)
        border_actions.addWidget(self.borderButton)
        self.verticalLayout_5.addLayout(border_actions)

        self.verticalLayout_5.addWidget(self.checkBox)
        self.verticalLayout_5.addWidget(self.fadeCheckBox)
        self.verticalLayout_5.addSpacing(6)
        self.verticalLayout_5.addWidget(
            self.replaceButton, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter
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

        self.horizontalLayout.removeItem(self.horizontalSpacer_9)
        self.horizontalLayout.removeItem(self.horizontalSpacer_10)
        self.horizontalLayout.insertWidget(0, self.resultsLabel)
        self.horizontalLayout.setSpacing(8)
        self.horizontalLayout.setContentsMargins(0, 0, 0, 0)
        self.horizontalLayout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        return self.horizontalLayout

    def _configure_results_grid(self):
        self.sleevesView.setFlow(QListView.Flow.TopToBottom)
        self.sleevesView.setWrapping(True)
        self.sleevesView.setResizeMode(QListView.ResizeMode.Adjust)
        self.sleevesView.setMovement(QListView.Movement.Static)
        self.sleevesView.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.sleevesView.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.sleevesView.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.sleevesView.setUniformItemSizes(True)
        self.sleevesView.setWordWrap(True)
        self.sleevesView.setIconSize(self.RESULT_ICON_SIZE)
        self.sleevesView.setGridSize(self.RESULT_ITEM_SIZE)
        self.sleevesView.setStyleSheet("""
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
        if not hasattr(self, "sleevesView"):
            return

        self.sleevesView.setIconSize(self.RESULT_ICON_SIZE)
        self.sleevesView.setGridSize(self.RESULT_ITEM_SIZE)
        self.sleevesView.doItemsLayout()

    def _adjust_image_sizes(self):
        if not hasattr(self, "editorPanel"):
            super()._adjust_image_sizes()
            return

        if self.editorPanel.width() <= 0 or self.editorPanel.height() <= 0:
            return

        available_height = max(140, self.editorPanel.height() - 34)
        available_width = max(96, self.editorPanel.width() // 3)
        target_height = max(
            140,
            min(
                self._max_image_size,
                available_height,
                int(available_width / self.SLEEVE_ASPECT_RATIO),
            ),
        )
        target_width = int(target_height * self.SLEEVE_ASPECT_RATIO)

        for label in (self.current, self.preview):
            label.setFixedSize(QSize(target_width, target_height))
            label.updateGeometry()

    def _queue_initial_layout_update(self):
        for delay in (0, 50, 150):
            QtCore.QTimer.singleShot(delay, self._refresh_layout_after_show)

    def _queue_layout_update(self):
        QtCore.QTimer.singleShot(0, self._refresh_layout_after_show)
        QtCore.QTimer.singleShot(25, self._refresh_layout_after_show)

    def _refresh_layout_after_show(self):
        self.sleeveSplitter.updateGeometry()
        self.editorPanel.updateGeometry()
        self.resultsPanel.updateGeometry()
        self._adjust_image_sizes()
        self._update_results_grid()

    def _persist_splitter_state(self):
        self._settings.setValue(
            "sleeves/splitter_state", self.sleeveSplitter.saveState()
        )

    def _set_editor_context(self, text):
        self.bundle.setText(text)
        self.label.setText(f"Sleeves · {text}")

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
                self.sleeveEdit.setText(file_path)
                self.preview.setPixmap(QPixmap(file_path))
                self.service.image_path = file_path
                break

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
        self.fadeCheckBox.clicked.connect(self._toggle_fade)
        self.favoriteBox.stateChanged.connect(self._toggle_favorite)
        self.favoritesBox.stateChanged.connect(self._toggle_favorites_filter)

    def _toggle_favorite(self, state):
        if self.selected and self.selected.favorite != (
            state == QtCore.Qt.CheckState.Checked.value
        ):
            self.selected.favorite = state == QtCore.Qt.CheckState.Checked.value
            session.commit()
            show_toast(
                self,
                "Favorite",
                "Sleeve favorite status updated",
                ToastPreset.SUCCESS_DARK,
            )

    def _toggle_favorites_filter(self, state):
        self.model.show_favorites = state == QtCore.Qt.CheckState.Checked.value
        if self.model.show_favorites:
            self.model.refresh()
            self.model.layoutChanged.emit()
        else:
            self.model.refresh()
            self.model.layoutChanged.emit()

    def _on_sleeve_clicked(self, index):
        self.selected = self.model.assets[index.row()]

        self.current.setPixmap(
            fetch_bundle_thumb(self.selected.bundle, (256, 375)).pixmap(256, 375)
        )
        self.service.bundle = self.selected.bundle
        self._set_editor_context(f"Editing {self.selected.bundle}")

        self.replaceButton.setEnabled(True)
        self.extractButton.setEnabled(True)
        self.restoreButton.setEnabled(True)
        self.copyButton.setEnabled(True)
        self.favoriteBox.setChecked(self.selected.favorite)
        hide_selection_helper(self)

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
        border_enabled = self.checkBox.isChecked()
        self.fadeCheckBox.setEnabled(border_enabled)

        if border_enabled:
            # For preview, we'll use a simple border - the actual fade effect will be applied during replacement
            self.preview.setStyleSheet(f"""
                #preview {{
                    border: 15px solid {self.service.border_color};
                }}
            """)
        else:
            self.preview.setStyleSheet("")
            self.fadeCheckBox.setChecked(False)

        self.service.border = border_enabled
        self.service.border_fade = self.fadeCheckBox.isChecked()

    def _toggle_fade(self):
        self.service.border_fade = self.fadeCheckBox.isChecked()
        # Update preview to show fade effect indication (we'll keep the simple border for preview)
        if self.fadeCheckBox.isChecked() and self.checkBox.isChecked():
            # Could add a visual indicator that fade is enabled, but for now keep simple border
            pass
